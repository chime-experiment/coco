Endpoints
================================

An endpoint configuration file should end with `.conf`. If it starts with `_`, it will be ignored.
The name of the endpoint will be the name of the file without the ending (for example a file
`foo.conf` would result in a `/foo` endpoint). The configuration needs
to be structured using `YAML <https://en.wikipedia.org/wiki/YAML>`_ using the following options:

group : `str`
    The name of the group of hosts this should forward to.
type : `str`
    (optional) The HTTP request method. Currently supported: `GET` and `POST`. Default: `GET`.
call : json block
    (optional) Specify where calls to this endpoint should get forwarded to by defining `forward`
    and `coco` inside this block.

    forward : `str` or list(str)
        (optional) Name(s) of endpoint(s) on the hosts in the specified group that requests should
        get forwarded to. If this is not defined, it is set to the name of the endpoint config
        file. Forwarding to external endpoints can be disabled by setting this to `null`.
    coco : str or list(str)
        (optional) Name(s) of other coco endpoint(s) that requests should get forwarded to.
before : `list(str)` or `json` block
    (optional) List or block of coco endpoints that will be called before anything else. The order
    they are called is not guaranteed. The endpoints can be given as strings containing the
    endpoint name or a blocks with the following options:

    identical : `str` or list(str)
        (optional) Name of value(s) to check for being identical between all hosts in specified
        group.
    value : `json` block
        (optional) Name of value(s) to check and the expected values (e.g.
        `my_string: "expected value"`)
    on_failure
        (optional) **TODO**: offer options for what to do if any of the above checks failed or if
        the request failed
after : `list(str)` or `json` block
    (optional) List or block of coco endpoints that will be called after anything else. The order
    they are called is not guaranteed. The endpoints can be given as strings containing the
    endpoint name or a blocks with the following options:

    identical : `str` or list(str)
        (optional) Name of value(s) to check for being identical between all hosts in specified
        group.
    value : `json` block
        (optional) Name of value(s) to check and the expected values (e.g.
        `my_string: "expected value"`)
    on_failure
        (optional) **TODO**: offer options for what to do if any of the above checks failed or if
        the request failed
callable : bool
    (optional) **TODO** If this is `False` coco will not accept calls to this endpoint from outside. Default
    `True`.
call_on_start : `bool`
    (optional) If this is `True`, coco will call this when coco starts. Default `False`.
values : json block
    (optional) If any request data (json) should get forwarded to the endpoints defined in the
    section `call`, they have to be listed here together with their type (e.g. `my_variable: int`).
send_state : str
    Path to a part of the internal state that should be used as request data. This will be updated
    with anything specified in the section `values` before forwarding.
save_state : str
    Path to a part of the internal state. Anything specified in the section `values` will be saved
    here.
get_state : str
    Path to a part of the internal state that should be returned. It is added to the result report
    (**TODO** add link here) under the section `state`.
schedule: `dict`
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
            (optional) The type of the state field to check. (Should be parseable by `pydoc.locate`.)
            Only required if value is specified.
        value : type specified above
            (optional) Require the state field have this value.
            If not specified, just check it exists.
