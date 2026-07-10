"""Coco client CLI implementation.

Program flow in this click app can be a bit opaque.  This is roughly
what's going on when the "coco" client is invoked as a program:

    1. click creates an instance of the `CliGroup` class to wrap the entry
        point.
    2. `CliGroup.main` is called on the instance to invoke the program.  This
        happens before most of click has started up.  This extracts the
        "--backend" and "--conf" arguments and stores their arguments in a dict
        that will eventually become the click context object (`ctx.obj`).
    3. `CliGroup.main` passes control to the normal `click.Group.main` which
        performs normal click parsing on the remaining command-line, stopping at
        the first non-option (which is the command to invoke), if any.
    4. The wrapped `entry` function is called.  This stores the global options
        parsed by click to the `ctx.obj` dict previously created.
    5. If "coco --help" is being run, `CliGroup.list_commands` is called to list
        all the avaiable commands in the top-level group.  Otherwise, in the
        case of a particular command being invoked, `CliGroup.get_command` is
        called to fetch the particular click.Command being invoked so command-
        line parsing can contiue.
    6. Both `CliGroup.list_commands` and `CliGroup.get_command` next call
        `CliGroup.init_coco` to fetch the coco config from the daemon, using the
        "--backend" and/or "--conf" options previously found (or envars) to
        determine the host/port of the daemon.  Once the config is returned,
        this function creates `EndpointCommand` instances for each endpoint
        defined, and adds them all to the `CliGroup` instance.  If an error
        occurs trying to contact the daemon, the error is recorded for later,
        but program flow continues.
    7. After creating all the endpoint commands, control passes to the normal
        `click.Group.list_commands` or `click.Group.get_command` and program
        flow now follows in the normal `click` way.
    8. Finally, at the end, in the case of a command being invoked,
        `CliGroup.invoke` takes the old-school 2-tuple coco client result
        produced by the command invocation and outputs it in the user-requested
        format.
"""

import asyncio
import http.client
import json
import os
import sys

import click
import yaml
from aiohttp import ClientSession, ContentTypeError

from . import metric, result
from .config import DEFAULT_PORT, load_config
from .endpoint import VALUE_TYPE


class EndpointCommand(click.Command):
    """A click Command for a single endpoint."""

    def __init__(self, endpoint):
        self.endpoint = endpoint
        name = endpoint["name"]

        # Holds user-facing names of endpoint values
        self._val_name = {}

        # Figure out short help.
        if "summary" in endpoint:
            # If a there's a "summary" use that.
            short_help = endpoint["summary"]
        elif "description" in endpoint:
            # If there's a description, use everything up to the first full stop.
            short_help = endpoint["description"]
            try:
                short_help = short_help[: short_help.index(". ")]
            except ValueError:
                # description is at most once sentence.  Use it all.
                pass
        else:
            # This is the unhelpful default
            short_help = f"Endpoint {name}"

        params, param_help = self._endpoint_params()

        help_ = (
            endpoint.get("description", endpoint.get("summary", "NO DESCRIPTION"))
            + param_help
        )

        # click initialisation
        super().__init__(
            name,
            short_help=short_help,
            help=help_,
            callback=self.callback,
            params=params,
        )

    def _endpoint_params(self):
        """Generate click command params based on the endpoint data."""

        params = []
        param_help_list = []

        # At most one list-type argument may be defined.  If we find one,
        # it will be stored here temporarily
        list_arg = None

        # Name of this endpoint
        ename = self.endpoint["name"]

        for name, val in sorted(self.endpoint.get("values", {}).items()):
            # Sanity check
            type_ = val["type"]
            if type_ not in VALUE_TYPE:
                raise click.ClickException(
                    f"Unknown parameter type {type_!r} in endpoint {ename}"
                )

            # Extract list itemtype for convenience
            if type_ == "list":
                item_type = val.get("item-type", "str")
            else:
                item_type = None

            # Is this an --option or an ARGUMENT (option is default)
            is_option = val.get("option", True)

            # Is this boolean-valued?
            is_flag = type_ == "bool" or item_type == "bool"

            # Figure out the param_decls.  This is a list whose first element
            # is always just "name" (which will be used for the keyword parameter
            # name).
            param_decls = [name]

            # For non-options, there are no more param_decls
            if is_option:
                # Add "params" to param_decls
                for param in val.get("params", ()):
                    if len(param) == 1:
                        param_decls.append("-" + param)
                    else:
                        param_decls.append("--" + param)

                # If there were no parameters, make one out of the name
                if len(param_decls) == 1:
                    param_decls.append(
                        ("-" if len(name) == 1 else "--")
                        + name.lower().replace("_", "-")
                    )

                # Add false-type params for bools
                if is_flag:
                    off_flags = val.get("off_flags", ())
                    if off_flags:
                        for flag in off_flags:
                            # The space-slash tells click these are a false-type options
                            if len(param) == 1:
                                param_decls.append(" /-" + param)
                            else:
                                param_decls.append(" /--" + param)
                    else:
                        # Create the false flag from the name
                        param_decls.append(" /--no-" + name.lower().replace("_", "-"))

            # unpack defaults from the dict
            _, param_type, param_help = VALUE_TYPE[item_type if item_type else type_]

            # override help text with config value, if given
            param_help = val.get("help", param_help)

            # For options, append a hint to the help. for lists
            if is_option and type_ == "list":
                if param_help[-1] not in ".!?":
                    param_help += "."
                param_help += " Use multiple times to specify each list element."

            # Instantiate the click.Parameter (Option or Argument)
            if is_option:
                self._val_name[name] = param_decls[1]
                param = click.Option(
                    param_decls,
                    type=param_type,
                    metavar=val.get("meta", None),
                    required=True,
                    multiple=(item_type is not None),
                    default=None,
                    is_flag=is_flag,
                    help=param_help,
                )
            else:
                self._val_name[name] = name.upper()
                param = click.Argument(
                    param_decls,
                    type=param_type,
                    metavar=val.get("meta", None),
                    required=True,
                    nargs=-1 if (item_type is not None) else 1,
                )

                # For non-options (arguments), we need to append the help text to
                # the command's help.  We collect them here.
                param_help_list.append((name.upper(), param_help))

            if item_type is not None and not is_option:
                # list-type arguements are special
                if list_arg:
                    # cocod should have already prevented this from happening.
                    raise click.ClickException(
                        "multiple list-type arguments in Endpoint {ename!r}!"
                    )
                list_arg = param
            else:
                # Otherwise, append the options to the parameter list
                params.append(param)

        if param_help_list:
            # Make the help, if any arguments were defined
            formatter = click.HelpFormatter(indent_increment=4)

            with formatter.section("Required Parameters"):
                formatter.write_dl(param_help_list)

            # The line with the bell (\b) will be deleted.  It tells click that
            # the text following is already formatted and shouldn't be reflowed.
            param_help = "\n\n\b\n" + formatter.getvalue()
        else:
            param_help = ""

        # A list argument goes at the end of the parameters, if one was defined
        if list_arg:
            params.append(list_arg)

        return params, param_help

    def callback(self, **kwargs):
        """Command callback

        This handles encoding of endpoint values and invoking the daemon's endpoint.

        Parameters
        ----------
        kwargs
            command-line data values
        """
        data = {}
        values = self.endpoint.get("values", {})
        for key, val in values.items():
            type_ = val["type"]

            if kwargs[key] is None:
                raise click.ClickException(
                    f"missing required parameter {self._val_name[key]!r}"
                )

            if type_ == "dict":
                try:
                    data[key] = json.loads(kwargs[key])
                except json.JSONDecodeError as e:
                    raise click.ClickException(
                        f"Failure parsing {self._val_name[key]!r}: {e}"
                    ) from e
            else:
                data[key] = kwargs[key]

            # Validate type conversion
            if type_ == "list":
                item_type, _, item_help = VALUE_TYPE[val.get("item-type", "str")]
                for idx, item in enumerate(data[key]):
                    if not isinstance(item, item_type):
                        raise click.ClickException(
                            f"Invalid value for element {idx} of "
                            f"{self._val_name[key]!r}: {item_help} expected"
                        )
            elif not isinstance(data[key], VALUE_TYPE[type_][0]):
                raise click.ClickException(
                    f"Invalid value for {self._val_name[key]!r}: "
                    f"{VALUE_TYPE[type_][2]} expected ({data[key]})"
                )

        return client_send_request(
            click.get_current_context(),
            self.name,
            type=self.endpoint["type"],
            **data,
        )


def client_send_request(
    ctx: click.Context, path: str, *, type: str | None = None, **data
):
    """Send a request to the daemon.

    Parameters
    ----------
    ctx : click.Context
        The click Context containing the coco config and values of the global options.
    path : str
        Endpoint path.
    type : str, optional
        HTTP request type.  Defaults to "GET".
    data : Any
        Other keyword arguments to this function are JSON-serialized and sent
        to the endpoint.

    Returns
    -------
    bool
        Success
    json or str
        The reply
    """

    # Were we able to initialise coco?
    if ctx.obj is None or "coco_config" not in ctx.obj:
        try:
            raise ctx.obj["config_error"]
        except KeyError:
            raise click.ClickException("Endpoint call attempted while unconfigured!")

    # Determine HTTP command
    if type is None:
        type_ = "get"
    else:
        type_ = type.lower()

    # Extract useful information from the click context
    host = ctx.obj["host"]
    port = ctx.obj["port"]
    metrics_port = ctx.obj["coco_config"]["metrics_port"]

    url = f"http://{host}:{port}/{path}"

    client_options = ctx.obj["options"]

    # Add report type
    data["coco_report_type"] = client_options["report"]

    # Short-circut for --show-call-only
    if client_options["show_call"]:
        return True, {"endpoint": url, "method": type_.upper(), "data": data}

    silent = client_options["silent"]
    if silent:
        refresh_time = 0
    else:
        refresh_time = client_options["refresh_time"]

    async def print_queue_size(metric_request_count):
        try:
            q_size = await metric.get("coco_queue_length_total", metrics_port, host)
        except RuntimeError as err:
            if not isinstance(err, asyncio.CancelledError):
                print(f"Couldn't get queue fill level from cocod: {err}")
            return
        print(
            f"\rThere are {int(q_size)} requests in the queue.",
            sep=" ",
            end="",
            flush=True,
        )
        if metric_request_count % 2:
            print(" ", sep=" ", end="", flush=True)
        else:
            print(".", sep=" ", end="", flush=True)

    async def send_request():
        if not silent:
            print("Sending request...")

        async with ClientSession() as session:
            try:
                command = getattr(session, type_)
                async with command(url, json=data) as resp:
                    try:
                        result = await resp.json()
                    except ContentTypeError:
                        result = {"Error": await resp.text()}
            except RuntimeError as e:
                return False, f"coco-client: Sending request failed: {e}"
            else:
                return True, result

    async def request_and_wait():
        """
        Send the request and while waiting get and print queue fill level metric.

        Returns
        -------
            Done task for request result.
        """
        main_request = asyncio.create_task(send_request())
        if refresh_time > 0:
            metric_request_count = 0
            while True:
                metric_request_count = metric_request_count + 1
                queue_size = asyncio.create_task(print_queue_size(metric_request_count))
                # Wait until either main request or request for metric is done
                done, _ = await asyncio.wait(
                    {main_request, queue_size}, return_when=asyncio.FIRST_COMPLETED
                )
                if main_request in done:
                    queue_size.cancel()
                    print("\n")
                    break

                # Wait a moment before getting metric again
                wait = asyncio.create_task(asyncio.sleep(refresh_time))
                # Cancel waiting in case main request is done
                done, _ = await asyncio.wait(
                    {main_request, wait}, return_when=asyncio.FIRST_COMPLETED
                )
                if main_request in done:
                    wait.cancel()
                    print("\n")
                    break
        return await main_request

    return asyncio.run(request_and_wait())


class CliGroup(click.Group):
    """click command group for the top-level CLI."""

    def __init__(self, *args, **kwargs):
        # Set to True after the client has loaded the coco config from the daemon
        self._coco_init = False
        super().__init__(*args, **kwargs)

    def _init_endpoints(self, endpoints):
        """Update the click command list with endpoint definitions."""
        for endpoint in endpoints:
            self.add_command(EndpointCommand(endpoint))

    def format_commands(self, ctx, formatter):
        """List commands and endpoints.

        This is a re-implementation of the parent method to force the
        separation of commands from endpoints.  If there are no endpoints,
        it will also try to output a hint as to why that might be.
        """
        commands = []
        endpoints = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue

            if isinstance(cmd, EndpointCommand):
                endpoints.append((subcommand, cmd))
            else:
                commands.append((subcommand, cmd))

        # allow for 3 times the default spacing
        limit = (
            formatter.width - 6 - max(len(cmd[0]) for cmd in [*commands, *endpoints])
        )

        if commands:
            rows = [
                (subcommand, cmd.get_short_help_str(limit))
                for subcommand, cmd in commands
            ]
            with formatter.section("Commands"):
                formatter.write_dl(rows)

        with formatter.section("Endpoints"):
            rows = [
                (subcommand, cmd.get_short_help_str(limit))
                for subcommand, cmd in endpoints
            ]
            if rows:
                formatter.write_dl(rows)
            elif "config_error" in ctx.obj:
                formatter.write_text(
                    "Endpoints not available.  Client configuration failed:"
                )
                formatter.write("\n")
                with formatter.indentation():
                    formatter.write_text(str(ctx.obj["config_error"]))
                formatter.write("\n")
                formatter.write_text("See 'coco --help-config'.")
            else:
                formatter.write_text(
                    "No endpoints found!  Is coco configured?  "
                    "See 'coco --help-config'."
                )

    def _init_coco(self, ctx: click.Context) -> None:
        """Initialise the coco client with the config provided by the server."""

        # If given on the command line, these have already been parsed out of it.
        backend = ctx.obj["backend"]
        config = ctx.obj["conf"]

        # If no back-end was given on the command line, look for one in the environment
        if backend is None:
            backend = os.environ.get("COCO_BACKEND", None)

        if backend is None:
            # If we _still_ have no backend, try to get it from a local config file
            coco_config = load_config(config, cli=True)

            host = coco_config["host"]
            port = coco_config["port"]
        else:
            # If the backend is an URI, drop the schema
            try:
                backend = backend[backend.index("://") + 3 :]
            except ValueError:
                pass

            # If the backend has path elements, drop them
            try:
                backend = backend[: backend.index("/")]
            except ValueError:
                pass

            # Split the user-supplied back-end
            try:
                host, port = backend.split(":")
            except ValueError:
                # In this case, only a host was given.  Assume the default port.
                host = backend
                port = DEFAULT_PORT

        # Remember for later
        ctx.obj["host"] = host
        try:
            ctx.obj["port"] = int(port)
        except (TypeError, ValueError) as e:
            raise click.ClickException(f"Invalid port {port!r} for backend.") from e

        # Get the coco config from the daemon
        try:
            conn = http.client.HTTPConnection(host, port, timeout=2)
            conn.request("GET", "/config", headers={"Host": host})
            res = conn.getresponse()
        except TimeoutError as e:
            raise click.ClickException(
                f"Timed-out trying to connect to {host}:{port}"
            ) from e
        except (OSError, http.client.HTTPException) as e:
            raise click.ClickException(
                f"Error reading from daemon ({host}:{port}): {e}"
            ) from e

        # Handle non-success
        if res.status != 200:
            raise click.ClickException(
                f"Unexpected response {res.status} from daemon while fetching config"
            )

        # Read config from server
        try:
            data = b""
            while chunk := res.read(1024):
                data += chunk
        except http.client.HTTPException as e:
            raise click.ClickException(str(e)) from e

        # Decode
        try:
            coco_config = json.loads(data)
        except json.JSONDecodeError as e:
            raise click.ClickError(f"Failure parsing config from server: {e}") from e

        # Record it
        ctx.obj["coco_config"] = coco_config

        # Configure click for the endpoints
        self._init_endpoints(coco_config["endpoints"])

    def init_coco(self, ctx: click.Context) -> None:
        """Initialise coco.

        Parameters
        ----------
        ctx
            The click Context
        """

        # Already done?
        if self._coco_init:
            return

        try:
            self._init_coco(ctx)
        except click.ClickException as e:
            # Save an error for later
            ctx.obj["config_error"] = e

        # coco init complete
        self._coco_init = True

    def invoke(self, ctx: click.Context) -> dict | None:
        """Invoke this command group.

        This is where we output the result of the client call.

        Returns
        -------
        dict | None
            If invocation succeded, returns the result of the invocation,
            if any.

        Raises
        ------
        click.ClickException
            The invocation did not succeed.
        """
        # Invoke the command in the normal click way.
        result = super().invoke(ctx)

        if result:
            # Result is a 2-tuple.  The first element is a bool indicating
            # success.  If successful, the second element is the result dict.
            # If not successful, the second element is an error string.
            if result[0]:
                if ctx.obj["options"]["json"]:
                    click.echo(json.dumps(result[1], indent=2))
                else:
                    click.echo(yaml.dump(result[1]))
                return result[1]
            # report an error
            raise click.ClickException(result[1])

        # No result
        return None

    def list_commands(self, ctx):
        """List commands.

        Ensures coco is initialised before command listing happens.
        """
        self.init_coco(ctx)

        return super().list_commands(ctx)

    def get_command(self, ctx, cmd_name):
        """Get command.

        Ensures coco is initialised before command retrieval happens.
        """
        self.init_coco(ctx)

        command = super().get_command(ctx, cmd_name)

        if command is None and "config_error" in ctx.obj:
            # If the user asked for a command that we don't
            # know about but configuration failed, it might
            # be because the user is anticipating an endpoint that's
            # not available.  Tell the user about the situation.
            raise click.NoSuchCommand(
                cmd_name,
                message=(
                    f"No such command {cmd_name!r}!\n"
                    + "This may be because client configuration failed:\n\n  "
                    + str(ctx.obj["config_error"])
                    + "\n\nFor information on configuring the coco client, "
                    + "see 'coco --help-config'"
                ),
                ctx=ctx,
            )

        return command

    def main(self, args=None, standalone_mode=True, **kwargs):
        """Execute the top-level command group.

        We need to pre-parse the argument list to capture -b and -c early and
        jam them into the context before regular click parsing starts.

        Parameters
        ----------
        args:
            The command line arguments.  If not given, sys.argv is used.
        standalone_mode:
            If False, exceptions are propagated to the caller.  Defaults to
            True, meaning exceptions are converted error messages and then
            the program will exit.
        kwargs:
            Other arguments are passed onwards.
        """

        if args is None:
            args = sys.argv[1:]

        # This will end up as ctx.obj
        obj = {"backend": None, "conf": None}

        # If obj was given in kwargs, delete it (just to be safe)
        try:
            del kwargs["obj"]
        except KeyError:
            pass

        # This is where we collect command-line args which filtered through the
        # preprocessing unhandled
        remaining_args = []

        # Look through args for --backend and/or --conf.  If found, their associated
        # arguments are moved to the context object and then they're deleted from the
        # command line.
        try:
            for idx, arg in enumerate(args):
                if arg == "-b" or arg == "--backend":
                    try:
                        obj["backend"] = args.pop(idx + 1)
                    except IndexError as e:
                        raise click.ClickException(
                            f"Option {arg!r} requires an argument."
                        ) from e
                elif arg == "-c" or arg == "--conf":
                    try:
                        obj["conf"] = args.pop(idx + 1)
                    except IndexError as e:
                        raise click.ClickException(
                            f"Option {arg!r} requires an argument."
                        ) from e
                elif arg.startswith("--backend="):
                    obj["backend"] = arg[10:]
                elif arg.startswith("--conf="):
                    obj["conf"] = arg[7:]
                elif arg.startswith("-b"):
                    # With click, if -b requires an argument, then a command-line
                    # arg like "-bsomething" is equivalent to having two arguments
                    # "-b" and "something"
                    obj["backend"] = arg[2:]
                elif arg.startswith("-c"):
                    obj["conf"] = arg[2:]
                elif not arg.startswith("-"):
                    # Preparsing ends at the first non-option.
                    # Copy everything left to remaining_args.
                    remaining_args += args[idx:]
                    break
                else:
                    remaining_args.append(arg)
        except click.ClickException as e:
            # It's too early in program flow for click to be able to deal with
            # these for us.
            if not standalone_mode:
                raise
            e.show()
            sys.exit(e.exit_code)

        # Pass reduced args and the new context object onwards
        return super().main(
            args=remaining_args, standalone_mode=standalone_mode, obj=obj, **kwargs
        )


# Invoked by the --help-config argument
def config_help(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    def _bullet(formatter, text):
        """write a bullet list item to the formatter"""
        formatter.write(
            click.wrap_text(
                "* " + text,
                initial_indent=" " * formatter.current_indent,
                subsequent_indent=" "
                * (formatter.current_indent + formatter.indent_increment),
            )
        )
        formatter.write_paragraph()

    formatter = click.HelpFormatter(indent_increment=4)

    formatter.write_text(
        "For most use cases, this coco client needs to be configured by being "
        "told where the coco daemon is running so it can fetch the list of "
        "available endpoints.  If the coco client is left unconfigured, most "
        "of its functionality will not be available."
    )
    formatter.write_paragraph()
    formatter.write_text(
        "There are several ways configration can be accomplished (in order of "
        "decreasing precedence):"
    )

    # blank line
    formatter.write("\n")

    # This is a bulleted list
    formatter.indent()
    _bullet(
        formatter,
        "using '-b' or '--backend' to specify the daemon host on the "
        "command-line.  This may include a port number.  If no port number is "
        f"given, the default port, {DEFAULT_PORT}, is used:",
    )
    formatter.write("\n")
    with formatter.indentation():
        with formatter.indentation():
            formatter.write_usage(
                prog="coco",
                args=f"--backend cocod.internal:{DEFAULT_PORT} [...]",
                prefix="",
            )
    formatter.write("\n")
    _bullet(
        formatter,
        "using the COCO_BACKEND environmental variable.  The value of this "
        "variable is interpreted the same was as an argument to '-b' would be.",
    )
    _bullet(
        formatter,
        "using a config file.  The path to the config file may be explicitly "
        "specified with the '-c' or '--conf' command-line option, given in the "
        "COCO_CONFIG_FILE environmental variable, or else be one of the default "
        "config file paths:",
    )
    formatter.write("\n")
    with formatter.indentation():
        with formatter.indentation():
            formatter.write_text("/etc/coco/coco.conf")
            formatter.write_text("/etc/xdg/coco/coco.conf")
            formatter.write_text("~/.config/coco/coco.conf")
        formatter.write("\n")
        formatter.write_text(
            "The config file is a YAML file with one required key ('host') and "
            "one optional key ('port').  Other data in the config file will be "
            "ignored:"
        )
        formatter.write("\n")
        with formatter.indentation():
            formatter.write_text("---")
            formatter.write_text("host: cocod.internal")
            formatter.write_text(f"port: {DEFAULT_PORT}")

    # Output help
    click.echo(formatter.getvalue())
    ctx.exit(0)


@click.group(cls=CliGroup, name="coco")
# These first two should never be matched (since the pre-parsing removes them)
# but if they are, they'll be ignored.  They're defined here so that they show
# up in the --help output.
@click.option(
    "-b",
    "--backend",
    metavar="HOST[:PORT]",
    expose_value=False,
    help=(
        "connect to coco daemon listening on HOST and PORT.  "
        f"If PORT is omitted, the default port, {DEFAULT_PORT}, is used.  "
        "Incompatible with --conf."
    ),
)
@click.option(
    "-c",
    "--conf",
    metavar="FILE",
    expose_value=False,
    help=(
        "read coco client config from FILE (in addition to the "
        "standard places).  If --backend is also specified, "
        "this is ignored."
    ),
)
# Legacy alias for --refresh-time
@click.option(
    "--client-refresh-time", deprecated=True, hidden=True, default=None, type=int
)
# Other "regular" options
@click.option(
    "--json/--yaml",
    "json",
    is_flag=True,
    default=None,
    help="Print style for output.  If one of these flags is used, --quiet is also "
    "turned on, unless --interactive is explicitly used.   The default is "
    "equivalent to: --interactive --yaml.",
)
@click.option(
    "-q",
    "--silent/--interactive",
    "--quiet",
    is_flag=True,
    default=None,
    help="Quiet mode ensures the output from coco is decodable as either YAML or "
    "JSON by suppressing all output except the result.  Quiet mode is "
    "automatically turned on if one of the output style flags (--json or --yaml) "
    "is used.  Use --interactive along with those flags to select an output "
    "style without turning on quiet mode.",
)
@click.option(
    "-r",
    "--report",
    metavar="TYPE",
    help=f"specify report type (choose from {result.TYPES})",
    show_default=True,
    default="CODES_OVERVIEW",
    type=click.Choice(result.TYPES, case_sensitive=False),
)
@click.option("-s", "--style", metavar="TYPE", help="Obsolete.  Use --json or --yaml.")
@click.option(
    "--show-call-only",
    is_flag=True,
    default=False,
    help="Instead of executing something, just print the endpoint call "
    "that would have happened.",
)
@click.option(
    "-t",
    "--refresh-time",
    metavar="SEC",
    type=int,
    default=2,
    show_default=True,
    help="Set refresh time for queue updates to SEC seconds.  A refresh time of "
    "zero disables queue updates completley.",
)
@click.option(
    "--help-config",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=config_help,
    help="Show information about configuring this client.",
)
@click.pass_obj
def entry(
    obj, report, style, json, refresh_time, client_refresh_time, show_call_only, silent
):
    """This is the coco client."""

    # legacy --style overrides --json or --yaml, and doesn't turn on quiet mode
    # like those flags do.  A --style value which isn't "json" or "yaml" is silently
    # ignored.
    if style == "json":
        json = True
        if silent is None:
            silent = False
    elif style == "yaml":
        json = False
        if silent is None:
            silent = False
    elif json is not None:
        # --json and --yaml turn on --silent, unless overriden
        if silent is None:
            silent = True
    else:
        # Default is --yaml --interactive
        json = False
        if silent is None:
            silent = False

    # Add all the global options to the click context.
    obj["options"] = {
        "report": report,
        "json": json,
        "refresh_time": client_refresh_time
        if client_refresh_time is not None
        else refresh_time,
        "show_call": show_call_only,
        "silent": silent,
    }


# BLOCKLIST COMMAND GROUP


def set_blocklist_hostlist(host: tuple, hosts: str | None) -> tuple:
    """Handles the HOST and --hosts lists to create a host list for the blocklist.

    Parameters
    ----------
    host : tuple
        A tuple of HOST values from click.
    hosts : str or None
        The --hosts value from click.

    Return
    ------
    list
        A list of hosts in either `host` or `hosts` with duplicates removed.
    """

    # turn the HOST tuple into a set to make it easier to combine with
    # --hosts if also given
    all_hosts = set(host)

    # De-jsonify --hosts and combine into all_hosts
    if hosts:
        try:
            json_hosts = json.load(hosts)
        except json.JSONDecodeError:
            raise click.BadParameter("--hosts must be a JSON list.")
        if not isinstance(json_hosts, list):
            raise click.BadParameter("--hosts must be a JSON list.")

        all_hosts.add(json_hosts)

    # Now covnert to list and return
    return list(all_hosts)


@click.command("get")
@click.pass_context
def get_blocklist(ctx):
    """Retrieve the current blocklist."""
    return client_send_request(ctx, "blocklist")


@click.command("add")
@click.option(
    "--hosts",
    type=str,
    default=None,
    hidden=True,
    deprecated="Provide multiple HOST arguments instead.",
    metavar="LIST",
)
@click.argument("host", type=str, required=False, nargs=-1)
@click.pass_context
def add_blocklist(ctx, hosts, host):
    """Add HOSTs to the blocklist.

    Multiple HOSTs may be given on the command line.  They will
    all be added."""

    hosts = set_blocklist_hostlist(host, hosts)
    if not hosts:
        raise click.ClickException("At least one HOST is required.")

    return client_send_request(ctx, "update-blocklist", command="add", hosts=hosts)


@click.command("remove")
@click.option(
    "--hosts",
    type=str,
    deprecated="Provide multiple HOST arguments instead.",
    hidden=True,
    metavar="LIST",
)
@click.argument("host", type=str, required=False, nargs=-1)
@click.pass_context
def remove_blocklist(ctx, hosts, host):
    """Remove HOSTs from the blocklist.

    Multiple HOSTs may be given on the command line.  They will
    all be removed."""

    hosts = set_blocklist_hostlist(host, hosts)
    if not hosts:
        raise click.ClickException("At least one HOST is required.")

    return client_send_request(ctx, "update-blocklist", command="remove", hosts=hosts)


@click.command("clear")
@click.pass_context
def clear_blocklist(ctx):
    """Empty the blocklist."""
    return client_send_request(ctx, "update-blocklist", command="clear")


@entry.group(invoke_without_command=True)
@click.pass_context
def blocklist(ctx):
    """Interact with the coco blocklist."""

    if ctx.invoked_subcommand is None:
        # Invoke the get command if no command was given
        click.echo("WARNING: assuming 'blocklist get'")
        return get_blocklist.invoke(ctx)
    return None


blocklist.add_command(get_blocklist)
blocklist.add_command(add_blocklist)
blocklist.add_command(remove_blocklist)
blocklist.add_command(clear_blocklist)


# Also create an "update-blocklist" command group for legacy reasons
@entry.group("update-blocklist", hidden=True, deprecated='Use "blocklist" instead.')
@click.pass_context
def update_blocklist(ctx):
    return blocklist.invoke(ctx)


update_blocklist.add_command(add_blocklist)
update_blocklist.add_command(remove_blocklist)
update_blocklist.add_command(clear_blocklist)


# STATE COMMAND GROUP


@entry.group
def state():
    """Interact with the coco state."""


@state.command("reset")
@click.pass_context
def reset_state(ctx):
    """Reset the coco state."""

    # This is a post even though there's no data to send.
    return client_send_request(ctx, "reset-state", type="POST")


@state.command("list")
@click.pass_context
def list_states(ctx):
    """List available saved states."""
    return client_send_request(ctx, "saved-states")


@state.command("save")
@click.argument("name", metavar="NAME")
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="If NAME already exists, overwrite it.",
)
@click.pass_context
def save_state(ctx, name, overwrite):
    """Save the current coco state.

    The save happens on the daemon server.  The name of the state will be NAME,
    which can be used later to load the state.  This name will also appear in the
    list of saved states returned by "state list".
    """
    return client_send_request(ctx, "save-state", name=name, overwrite=overwrite)


@state.command("load")
@click.argument("name", metavar="NAME")
@click.pass_context
def load_state(ctx, name):
    """Load a saved state.

    This replaces the daemon's currently active state with the
    state previously saved as NAME."""
    return client_send_request(ctx, "load-state", name=name)


# Legacy state commands


@entry.command("reset-state", hidden=True, deprecated='Use "state reset" instead.')
@click.pass_context
def legacy_reset_state(ctx):
    return client_send_request(ctx, "reset-state", type="POST")


@entry.command("saved-states", hidden=True, deprecated='Use "state reset" instead.')
@click.pass_context
def legacy_list_states(ctx):
    return client_send_request(ctx, "saved-states")


@entry.command("save-state", hidden=True, deprecated='Use "state save" instead.')
@click.argument("name", metavar="NAME")
@click.option("--overwrite", is_flag=True, default=False)
@click.pass_context
def legacy_save_state(ctx, name, overwrite):
    return client_send_request(ctx, "save-state", name=name, overwrite=overwrite)


@entry.command("load-state", hidden=True, deprecated='Use "state load" instead.')
@click.argument("name", metavar="NAME")
@click.pass_context
def legacy_load_state(ctx, name):
    return client_send_request(ctx, "load-state", name=name)


# CONFIG COMMAND GROUP


@entry.group()
def config():
    """Interact with the coco config."""
    pass


@config.command("get")
@click.pass_context
def get_config(ctx):
    """Print the coco daemon config."""
    if "coco_config" in ctx.obj:
        if "options" in ctx.obj and ctx.obj["options"]["show_call"]:
            # This command doesn't call an endpoint, but a user using
            # "coco --show-call-only config get" probably wants to know
            # how to get the config from the daemon, so gin up the
            # endpoint that they would need to call
            return True, {
                "endpoint": (
                    "http://"
                    + ctx.obj["coco_config"]["host"]
                    + ":"
                    + str(ctx.obj["coco_config"]["port"])
                    + "/config"
                ),
                "method": "GET",
            }
        return True, ctx.obj["coco_config"]

    try:
        raise ctx.obj["config_error"]
    except KeyError as e:
        raise click.ClickException("Endpoint call attempted while unconfigured!") from e


# Legacy config commands


@entry.command("get-coco-config", hidden=True, deprecated='Use "config get" instead.')
@click.pass_context
def legacy_get_config(ctx):
    return get_config.invoke(ctx)


if __name__ == "__main__":
    entry()
