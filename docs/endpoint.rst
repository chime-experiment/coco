Endpoints
================================

An endpoint configuration file should end with `.conf`. If it starts with `_`, it will be ignored.
The name of the endpoint will be the name of the file without the ending (for example a file
`foo.conf` would result in a `/foo` endpoint). The configuration needs
to be structured using `YAML <https://en.wikipedia.org/wiki/YAML>`_ using the following options:

group : `str`
    The name of the group of hosts this should forward to.
enforce_group : bool
    If this is true, this endpoint will not accept a hosts parameter and always forward to the
    group configured here.
type : `str`
    (optional) The HTTP request method. Currently supported: `GET` and `POST`. Default: `GET`.
call : dict
    (optional) Specify where calls to this endpoint should get forwarded to by defining `forward`
    and `coco` inside this block.

    forward : `str` or dict or list(str or dict)
        External endpoint(s), see [Forwards](#forwards). If this is not defined, the coco endpoint
        will try to forward to an endpoint with the name of the endpoint config file. Forwarding
        to external endpoints can be disabled by setting this to `null`.
        The order they are called is not guaranteed.
    coco : str or dict or list(str or dict)
        (optional) Internal coco endpoint(s), see [Forwards](#forwards). The order they are called
        is not guaranteed.
before : `str` or dict or list(str or dict)
    (optional) Internal coco endpoint(s) that will be called before anything else, see
    [Forwards](#forwards). The order they are called is not guaranteed.
after : `str` or dict or list(str or dict)
    (optional) Internal coco endpoint(s) that will be called after anything else, see
    [Forwards](#forwards). The order they are called is not guaranteed.
callable : bool
    (optional) **TODO** If this is `False` coco will not accept calls to this endpoint from outside. Default
    `True`.
call_on_start : `bool`
    (optional) If this is `True`, coco will call this when coco starts. Default `False`.
values : dict
    (optional) If any request data (json) should get forwarded to the endpoints defined in the
    section `call`, they have to be listed here together with their type (e.g. `my_variable: int`).
send_state : str
    Path to a part of the internal state that should be used as request data. This will be updated
    with anything specified in the section `values` before forwarding.
save_state : str or list(str)
    Path to a part of the internal state. Anything specified in the section `values` will be saved
    here. If this is a list, the values will be stored in each of the given paths.
get_state : str
    Path to a part of the internal state that should be returned. It is added to the result report
    (**TODO** add link here) under the section `state`.
set_state : dict
    Set a value in coco's state in case the endpoint call was successful. Should have the form
    `<path/to/state>: <value>`.
schedule : `dict`
    (optional) Schedule this endpoint to be called periodically. Only endpoints that do not require
    arguments (the 'values' block) can be scheduled.

    period : `float`
        The period in seconds between calls.
    require_state : `dict` of `list(dict)`
        (optional) Set conditions on the running state that must be satisfied for the scheduler to
        call the endpoint. Multiple conditions can be specified as a list.

        path : `str`
            Path to state field to check.
        type : `str`
            The type of the state field to check. (Should be parseable by `pydoc.locate`.)
        value : type specified above
            (optional) Require the state field have this value.
            If not specified, just check path exists with correct type.
timestamp : str
    (optional) Set a path and name to where to write a timestamp to the state after *successful*
    endpoint calls.


Forwards
==========
A forward is described by the configuration as either a `str` or `dict`.

A `str` would just be the name of the endpoint to forward to. this can be internal (a coco endpoint
) or external.
If an entry is a dict, it can have the following options:

name : str
    Name of the endpoint to forward to.
request : dict
    Any request data to add to the forwarded call.
reply : dict
    See [Reply Checks](#reply-checks).
on_failure : dict
    call : str
        Another coco endpoint that should get called in case the reply from any host didn't
        pass.
    call_single_host : str
        Another coco endpoint that should get called for each host whose reply didn't pass the
        check.
save_reply_to_state : str
    Internal state path. The replies of all hosts will be merged and saved here. If replies
    include different fields, all fields will be saved in the state. If replies include
    different values for the same field, just one of them will be saved.


Checks
================================

Reply Checks
--------------

If the variables don't match in the reply from any host, the forwarding will be considered failed
for these hosts.

identical : list(str)
    Names of variables to check for being identical in the replies of all hosts.
value : dict(str, any)
    Names of variables to check and the expected values (e.g. my_string: "expected value").
type : dict(str, str)
    Names of variables to check and the expected types (e.g. my_var: float).
state : str or dict[str, str]
    Compare the reply with a part of the internal state. If this is a string, it should be the path
    to a part of the internal state. The whole reply will be compared to that part of the state.
    If a dict is given here, it should have names of expected reply fields and values should be
    paths to the internal state to compare with.
state_hash : dict[str, str]
    Compare a hash that is expected in a field of the reply with a hash calculated for a part of
    the state. Keys should be fields of the reply that contain a hash and values should be paths to
    the internal state. The hash of the state under this path will be computed and compared with
    the one from the reply.
