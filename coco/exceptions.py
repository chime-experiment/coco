"""Custom exceptions for coco."""


class CocoException(Exception):
    """Coco base exception type.

    Parameters
    ----------
    message
        Exception message.
    status_code
        HTTP status code to return (overrides the default in each subclass).
    context
        Extra context that will be returned in the JSON.
    """

    def __init__(self, message: str, status_code: int = None, context: dict = None):
        self.message = message
        self.context = context
        if status_code:
            self.status_code = status_code

    def to_dict(self) -> dict:
        """Get the exception as a JSON serialisable dictionary.

        Returns
        -------
        d
            The exception as a dict.
        """
        d = {"status_code": self.status_code, "message": self.message}

        if self.context:
            d["context"] = self.context

        return d


class InvalidUsage(CocoException):
    """An Exception resulting from improper client usage."""

    status_code = 400


class InvalidMethod(CocoException):
    """An Exception resulting from calling an incorrect method."""

    status_code = 405


class InvalidPath(CocoException):
    """An Exception resulting from calling an incorrect endpoint URL."""

    status_code = 404


class ConfigError(CocoException):
    """Exception for errors found in the config."""

    status_code = 500


class InternalError(CocoException):
    """Exception for coco internal errors."""

    status_code = 500
