from enum import Enum
from typing import Final

DEFAULT_API_ORIGIN: Final = "https://api.inngest.com/"
DEFAULT_EVENT_ORIGIN: Final = "https://inn.gs/"
DEV_SERVER_ORIGIN: Final = "http://127.0.0.1:8288/"
LANGUAGE: Final = "py"
VERSION: Final = "0.1.0"


class EnvKey(Enum):
    BASE_URL = "INNGEST_BASE_URL"
    EVENT_KEY = "INNGEST_EVENT_KEY"
    SIGNING_KEY = "INNGEST_SIGNING_KEY"


class ErrorCode(Enum):
    DEV_SERVER_REGISTRATION_NOT_ALLOWED = "DEV_SERVER_REGISTRATION_NOT_ALLOWED"
