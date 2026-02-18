"""
Constants and configuration values for Connect.
"""

import signal

import websockets

from inngest._internal import server_lib

# Signals that trigger graceful shutdown
DEFAULT_SHUTDOWN_SIGNALS = [signal.SIGINT, signal.SIGTERM]

# Framework identifier for Connect protocol
FRAMEWORK = server_lib.Framework.CONNECT

# WebSocket subprotocol identifier
PROTOCOL = websockets.Subprotocol("v0.connect.inngest.com")

# ============================================================================
# Timing Constants
# ============================================================================

# Interval between heartbeat messages sent to the server (seconds)
HEARTBEAT_INTERVAL_SEC = 10

# Maximum number of attempts for the initial connection start request
MAX_CONN_INIT_ATTEMPTS = 5

# Delay between connection start request retries (seconds)
CONN_INIT_RETRY_INTERVAL_SEC = 5

# Delay after WebSocket connect before checking connection state (seconds).
# This allows time for the initial handshake to complete.
POST_CONNECT_SETTLE_SEC = 1

# Delay before reconnecting after a connection error (seconds)
RECONNECTION_DELAY_SEC = 5

# ============================================================================
# Size Constants
# ============================================================================

# Inngest servers are configured to send up to 4 MB, but we'll set a higher
# limit to be safe
MAX_MESSAGE_SIZE = 5 * 1024 * 1024  # 5 MB

# Maximum size of the unacked message buffer (bytes). Messages exceeding this
# limit cause oldest messages to be evicted. This should probably be
# user-configurable.
DEFAULT_MAX_BUFFER_SIZE_BYTES = 1024 * 1024 * 500  # 500MB
