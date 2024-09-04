"""
Simulate Inngest function execution without an Inngest server.

NOT STABLE! This is an experimental feature and may change in the future. If
you'd like to depend on it, we recommend copying this directory into your source
code.
"""

from .consts import Status, Timeout
from .trigger import trigger

__all__ = [
    "Status",
    "Timeout",
    "trigger",
]
