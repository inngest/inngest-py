"""
Connect creates a persistent outbound connection to Inngest. Compared to our "serve" functions, Connect:
- Doesn't require exposing your app to the public internet.
- Is lower latency.
- Avoids HTTP timeouts.

Note that Connect does not work with serverless platforms: you must run your app
in a long-lived process. If you're using a serverless platform, you should use
our "serve" functions instead.
"""

from ._internal.connect import connect
from ._internal.models import ConnectionState

__all__ = ["connect", "ConnectionState"]
