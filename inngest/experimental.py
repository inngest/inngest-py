"""
Experimental entrypoint for the Inngest SDK.

Does not follow semantic versioning!
"""

from ._middleware.encryption import EncryptionMiddleware

__all__ = ["EncryptionMiddleware"]
