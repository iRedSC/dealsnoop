"""Shared exceptions for dealsnoop."""


class LocationResolutionError(ValueError):
    """Raised when a city code cannot be resolved to a human-readable location name."""
