
class CocoException(Exception):

    def __init__(self, message, status_code=500, context=None):
        self.message = message
        self.status_code = status_code
        self.context = context

    def to_dict(self) -> dict:
        """Get the exception as a JSON serialisable dictionary.

        Returns
        -------
        d
            The exception as a dict.
        """

        d = {'status_code': self.status_code, 'message': self.message}

        if self.context:
            d["context"] = self.context

        return d


class InvalidUsage(CocoException):
    """An Exception resulting from improper client usage.
    """
    status_code = 400


class InvalidMethod(CocoException):
    """An Exception resulting from calling an incorrect method.
    """
    status_code = 405


class InvalidPath(CocoException):
    """An Exception resulting from calling an incorrect endpoint URL.
    """
    status_code = 404
