import websockets

from inngest._internal import server_lib

_default_shutdown_signals = ["SIGINT", "SIGTERM"]
_framework = server_lib.Framework.CONNECT
_heartbeat_interval_sec = 10
_protocol = websockets.Subprotocol("v0.connect.inngest.com")
