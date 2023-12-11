import enum
import typing

DEFAULT_API_ORIGIN: typing.Final = "https://api.inngest.com/"
DEFAULT_EVENT_ORIGIN: typing.Final = "https://inn.gs/"
DEV_SERVER_ORIGIN: typing.Final = "http://127.0.0.1:8288/"
LANGUAGE: typing.Final = "py"
ROOT_STEP_ID: typing.Final = "step"
VERSION: typing.Final = "0.2.3"


class EnvKey(enum.Enum):
    API_BASE_URL = "INNGEST_API_BASE_URL"
    EVENT_API_BASE_URL = "INNGEST_EVENT_API_BASE_URL"
    EVENT_KEY = "INNGEST_EVENT_KEY"
    SERVE_ORIGIN = "INNGEST_SERVE_ORIGIN"
    SERVE_PATH = "INNGEST_SERVE_PATH"
    SIGNING_KEY = "INNGEST_SIGNING_KEY"


class ErrorCode(enum.Enum):
    DISALLOWED_REGISTRATION_INITIATOR = "disallowed_registration_initiator"
    INVALID_BASE_URL = "invalid_base_url"
    INVALID_BODY = "invalid_body"
    INVALID_FUNCTION_CONFIG = "invalid_function_config"
    INVALID_REQUEST_SIGNATURE = "invalid_request_signature"
    MISMATCHED_SYNC = "mismatched_sync"
    MISSING_EVENT_KEY = "missing_event_key"
    MISSING_FUNCTION = "missing_function"
    MISSING_HEADER = "missing_header"
    MISSING_SIGNING_KEY = "missing_signing_key"
    REGISTRATION_ERROR = "registration_error"
    UNKNOWN = "unknown"
    UNSERIALIZABLE_OUTPUT = "unserializable_output"


class Framework(enum.Enum):
    DJANGO = "django"
    FAST_API = "fast_api"
    FLASK = "flask"
    TORNADO = "tornado"


class HeaderKey(enum.Enum):
    CONTENT_TYPE = "Content-Type"
    EXPECTED_SERVER_KIND = "X-Inngest-Expected-Server-Kind"
    FRAMEWORK = "X-Inngest-Framework"
    NO_RETRY = "X-Inngest-No-Retry"
    SDK = "X-Inngest-SDK"
    SERVER_KIND = "X-Inngest-Server-Kind"
    SERVER_TIMING = "Server-Timing"
    SIGNATURE = "X-Inngest-Signature"
    USER_AGENT = "User-Agent"


class QueryParamKey(enum.Enum):
    FUNCTION_ID = "fnId"
    STEP_ID = "stepId"


class InternalEvents(enum.Enum):
    FUNCTION_FAILED = "inngest/function.failed"


class ServerKind(enum.Enum):
    CLOUD = "cloud"
    DEV_SERVER = "dev"
