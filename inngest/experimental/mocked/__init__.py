"""
Simulate Inngest function execution without an Inngest server.
"""

from .consts import Status, Timeout
from .trigger import trigger

__all__ = [
    "Status",
    "Timeout",
    "trigger",
]
