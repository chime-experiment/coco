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
call : dict
    (optional) Specify where calls to this endpoint should get forwarded to by defining `forward`
    and `coco` inside this block.

    forward : `str` or list(str) or dict
        (optional) Name(s) of endpoint(s) on the hosts in the specified group that requests should
        get forwarded to. If this is not defined, it is set to the name of the endpoint config
        file. Forwarding to external endpoints can be disabled by setting this to `null`.
        This can also be a dict / block that uses the endpoint names as keys and specifies
        additional options:

        reply : dict
            A dictionary that should have keys like the expected reply fields and can then specify
            the expected type or value:

            type : str
                The expected type of this variable in the reply. If the types don't match in the
                reply from any host, the forwarding will be considered failed for these hosts.
            value : any
                **TODO**
        on_failure : dict
            call : str
                Another coco endpoint that should get called in case the reply from any host didn't
                pass.
            call_single_host : str
                **TODO** Another coco endpoint that should get called for a single host onle in
                case the reply from that host didn't pass.
        save_reply_to_state : str
            Internal state path. The replies of all hosts will be merged and saved here. If replies
            include different fields, all fields will be saved in the state. If replies include
            different values for the same field, just one of them will be saved.
    coco : str or list(str)
        (optional) Name(s) of other coco endpoint(s) that requests should get forwarded to.
before : `list(str)` or dict
    (optional) List or block of coco endpoints that will be called before anything else. The order
    they are called is not guaranteed. The endpoints can be given as strings containing the
    endpoint name or a blocks with the following options:

    identical : `str` or list(str)
        (optional) Name of value(s) to check for being identical between all hosts in specified
        group.
    value : dict
        (optional) Name of value(s) to check and the expected values (e.g.
        `my_string: "expected value"`)
    on_failure
        (optional) **TODO**: offer options for what to do if any of the above checks failed or if
        the request failed
after : `list(str)` or dict
    (optional) List or block of coco endpoints that will be called after anything else. The order
    they are called is not guaranteed. The endpoints can be given as strings containing the
    endpoint name or a blocks with the following options:

    identical : `str` or list(str)
        (optional) Name of value(s) to check for being identical between all hosts in specified
        group.
    value : dict
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
values : dict
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
