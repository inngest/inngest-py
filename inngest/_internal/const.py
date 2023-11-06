import enum
import typing

DEFAULT_API_ORIGIN: typing.Final = "https://api.inngest.com/"
DEFAULT_EVENT_ORIGIN: typing.Final = "https://inn.gs/"
DEV_SERVER_ORIGIN: typing.Final = "http://127.0.0.1:8288/"
LANGUAGE: typing.Final = "py"
ROOT_STEP_ID: typing.Final = "step"
VERSION: typing.Final = "0.1.3"


class EnvKey(enum.Enum):
    BASE_URL = "INNGEST_BASE_URL"
    EVENT_KEY = "INNGEST_EVENT_KEY"
    SIGNING_KEY = "INNGEST_SIGNING_KEY"


class ErrorCode(enum.Enum):
    DISALLOWED_REGISTRATION_INITIATOR = "disallowed_registration_initiator"
    INVALID_BASE_URL = "invalid_base_url"
    INVALID_BODY = "invalid_body"
    INVALID_FUNCTION_CONFIG = "invalid_function_config"
    INVALID_REQUEST_SIGNATURE = "invalid_request_signature"
    INVALID_TRANSFORM = "invalid_transform"
    MISMATCHED_SYNC = "mismatched_sync"
    MISSING_EVENT_KEY = "missing_event_key"
    MISSING_FUNCTION = "missing_function"
    MISSING_HEADER = "missing_header"
    MISSING_PARAM = "missing_param"
    MISSING_SIGNING_KEY = "missing_signing_key"
    REGISTRATION_ERROR = "registration_error"
    UNKNOWN = "unknown"
    UNSERIALIZABLE_OUTPUT = "unserializable_output"


class Framework(enum.Enum):
    FAST_API = "fast_api"
    FLASK = "flask"
    TORNADO = "tornado"


class HeaderKey(enum.Enum):
    CONTENT_TYPE = "Content-Type"
    FORWARDED_FOR = "X-Forwarded-For"
    FRAMEWORK = "X-Inngest-Framework"
    NO_RETRY = "X-Inngest-No-Retry"
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
