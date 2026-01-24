import signal

import websockets

from inngest._internal import server_lib

_default_shutdown_signals = [signal.SIGINT, signal.SIGTERM]
_framework = server_lib.Framework.CONNECT
_heartbeat_interval_sec = 10
_protocol = websockets.Subprotocol("v0.connect.inngest.com")

# Inngest servers are configured to send up to 4 MB, but we'll set a higher
# limit to be safe
MAX_MESSAGE_SIZE = 5 * 1024 * 1024  # 5 MB
