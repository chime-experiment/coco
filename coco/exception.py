"""Exceptions for coco."""


class CocoException(Exception):
    """Base class for coco exceptions."""

    pass


class CocoConfigError(CocoException):
    """Exception for errors found in the config."""

    def __init__(self, message):
        self.message = message
