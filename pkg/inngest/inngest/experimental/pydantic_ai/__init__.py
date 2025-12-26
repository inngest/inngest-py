"""
Helper library wrapping Pydantic AI calls with Inngest.

NOT STABLE! This is an experimental feature and may change in the future. If
you'd like to depend on it, we recommend copying this directory into your source
code.
"""

from ._agent import InngestAgent
from ._serializer import Serializer

__all__ = ["InngestAgent", "Serializer"]
