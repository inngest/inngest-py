import enum
import typing

DEFAULT_API_ORIGIN: typing.Final = "https://api.inngest.com/"
DEFAULT_EVENT_ORIGIN: typing.Final = "https://inn.gs/"
DEV_SERVER_ORIGIN: typing.Final = "http://127.0.0.1:8288/"
LANGUAGE: typing.Final = "py"
ON_FAILURE_ID_SUFFIX: typing.Final = "-failure"
ROOT_STEP_ID: typing.Final = "step"
VERSION: typing.Final = "0.1.0"


class EnvKey(enum.Enum):
    BASE_URL = "INNGEST_BASE_URL"
    EVENT_KEY = "INNGEST_EVENT_KEY"
    SIGNING_KEY = "INNGEST_SIGNING_KEY"


class ErrorCode(enum.Enum):
    DEV_SERVER_REGISTRATION_NOT_ALLOWED = "dev_server_registration_not_allowed"
    INVALID_BASE_URL = "invalid_base_url"
    INVALID_FUNCTION_CONFIG = "invalid_function_config"
    INVALID_PARAM = "invalid_param"
    INVALID_REQUEST_SIGNATURE = "invalid_request_signature"
    INVALID_RESPONSE_SHAPE = "invalid_response_shape"
    MISMATCHED_SYNC = "mismatched_sync"
    MISSING_EVENT_KEY = "missing_event_key"
    MISSING_FUNCTION = "missing_function"
    MISSING_HEADER = "missing_header"
    MISSING_PARAM = "missing_param"
    MISSING_SIGNING_KEY = "missing_signing_key"
    UNSERIALIZABLE_OUTPUT = "unserializable_output"


class HeaderKey(enum.Enum):
    CONTENT_TYPE = "Content-Type"
    FORWARDED_FOR = "X-Forwarded-For"
    FRAMEWORK = "X-Inngest-Framework"
    NO_RETRY = "X-Inngest-No-Retry"
    REAL_IP = "X-Real-IP"
    SDK = "X-Inngest-SDK"
    SERVER_KIND = "X-Inngest-Server-Kind"
    SERVER_TIMING = "Server-Timing"
    SIGNATURE = "X-Inngest-Signature"
    USER_AGENT = "User-Agent"


class InternalEvents(enum.Enum):
    FUNCTION_FAILED = "inngest/function.failed"


class ServerKind(enum.Enum):
    CLOUD = "cloud"
    DEV_SERVER = "dev"
