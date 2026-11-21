class SwidgetException(Exception):
    """Base exception for device errors."""


class SwidgetAuthError(SwidgetException):
    """The device rejected the access key."""


class SwidgetUnsupportedDevice(SwidgetException):
    """The device reports a host type this library does not know."""
