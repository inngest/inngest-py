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
    DEV_SERVER_REGISTRATION_NOT_ALLOWED = "dev_server_registration_not_allowed"
    INVALID_BASE_URL = "invalid_base_url"
    INVALID_REQUEST_SIGNATURE = "invalid_request_signature"
    INVALID_RESPONSE_SHAPE = "invalid_response_shape"
    MISSING_EVENT_KEY = "missing_event_key"
    MISSING_FUNCTION = "missing_function"
    MISSING_HEADER = "missing_header"
    MISSING_PARAM = "missing_param"
    MISSING_SIGNING_KEY = "missing_signing_key"


class HeaderKey(Enum):
    CONTENT_TYPE = "Content-Type"
    FORWARDED_FOR = "X-Forwarded-For"
    FRAMEWORK = "X-Inngest-Framework"
    NO_RETRY = "X-Inngest-No-Retry"
    REAL_IP = "X-Real-IP"
    SDK = "X-Inngest-SDK"
    SERVER_TIMING = "Server-Timing"
    SIGNATURE = "X-Inngest-Signature"
    USER_AGENT = "User-Agent"
