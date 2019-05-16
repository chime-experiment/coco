"""coco endpoint module."""


class Endpoint:
    """
    An endpoint.

    Does whatever the config says.
    """

    def __init__(self, name, conf, callback, slacker, master):
        self.name = name
        self.group = conf.get("group")
        self.callable = conf.get("callable", False)
        self.slack = conf.get("slack")
        self.check = conf.get("check")
        self.callback = callback
        self.slacker = slacker
        self.master = master

        if conf.get("call_on_start", False):
            self.call()

    def call(self):
        """
        Call the endpoint.

        Returns
        -------
        :class:`Result`
            The result of the endpoint call.
        """
        if self.slack:
            self.slacker.send(self.slack.get("message", self.name), self.slack.get("channel"))
        self.callback(self.name)

        if self.check:
            for check in self.check:
                endpoint = list(check.keys())[0]
                options = check[list(check.keys())[0]]
                result = self.master.call_endpoint(endpoint)
                print(result)
