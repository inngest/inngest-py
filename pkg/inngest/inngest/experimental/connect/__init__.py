"""
Experimental support for the Inngest Connect feature.

This module is experimental and may have breaking changes that are not reflected
in semantic versioning.
"""

from .connect import connect
from .models import ConnectionState

__all__ = ["connect", "ConnectionState"]
