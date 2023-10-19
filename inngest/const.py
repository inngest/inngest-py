from enum import Enum
from typing import Final

DEFAULT_INNGEST_BASE_URL: Final = "https://api.inngest.com/"
DEFAULT_INNGEST_EVENT_BASE_URL: Final = "https://inn.gs/"
DEFAULT_DEV_SERVER_HOST: Final = "http://127.0.0.1:8288/"
LANGUAGE: Final = "py"
VERSION: Final = "0.0.1"


class EnvKey(Enum):
    BASE_URL = "INNGEST_BASE_URL"
    EVENT_KEY = "INNGEST_EVENT_KEY"
    SIGNING_KEY = "INNGEST_SIGNING_KEY"


class ErrorCode(Enum):
    DEV_SERVER_REGISTRATION_NOT_ALLOWED = "DEV_SERVER_REGISTRATION_NOT_ALLOWED"
