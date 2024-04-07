import enum
import typing

DEFAULT_API_ORIGIN: typing.Final = "https://api.inngest.com/"
DEFAULT_EVENT_ORIGIN: typing.Final = "https://inn.gs/"
DEV_SERVER_ORIGIN: typing.Final = "http://127.0.0.1:8288/"
LANGUAGE: typing.Final = "py"
ROOT_STEP_ID: typing.Final = "step"
VERSION: typing.Final = "0.3.8"


class EnvKey(enum.Enum):
    API_BASE_URL = "INNGEST_API_BASE_URL"
    DEV = "INNGEST_DEV"
    EVENT_API_BASE_URL = "INNGEST_EVENT_API_BASE_URL"
    EVENT_KEY = "INNGEST_EVENT_KEY"
    ENV = "INNGEST_ENV"

    # Railway deployment's git branch
    # https://docs.railway.app/develop/variables#railway-provided-variables
    RAILWAY_GIT_BRANCH = "RAILWAY_GIT_BRANCH"

    # Render deployment's git branch
    # https://render.com/docs/environment-variables#all-services
    RENDER_GIT_BRANCH = "RENDER_GIT_BRANCH"

    SERVE_ORIGIN = "INNGEST_SERVE_ORIGIN"
    SERVE_PATH = "INNGEST_SERVE_PATH"
    SIGNING_KEY = "INNGEST_SIGNING_KEY"

    # Vercel deployment's git branch
    # https://vercel.com/docs/concepts/projects/environment-variables/system-environment-variables#system-environment-variables
    VERCEL_GIT_BRANCH = "VERCEL_GIT_COMMIT_REF"


class ErrorCode(enum.Enum):
    ASYNC_UNSUPPORTED = "async_unsupported"
    BODY_INVALID = "body_invalid"
    EVENT_KEY_UNSPECIFIED = "event_key_unspecified"
    FUNCTION_CONFIG_INVALID = "function_config_invalid"
    FUNCTION_NOT_FOUND = "function_not_found"
    HEADER_MISSING = "header_missing"
    NON_RETRIABLE_ERROR = "non_retriable_error"
    OUTPUT_UNSERIALIZABLE = "output_unserializable"
    QUERY_PARAM_MISSING = "query_param_missing"
    REGISTRATION_FAILED = "registration_failed"
    SERVER_KIND_MISMATCH = "server_kind_mismatch"
    SIGNING_KEY_UNSPECIFIED = "signing_key_unspecified"
    SIG_VERIFICATION_FAILED = "sig_verification_failed"
    STEP_ERRORED = "step_errored"
    STEP_UNEXPECTED = "step_unexpected"
    UNKNOWN = "unknown"
    URL_INVALID = "url_invalid"


class Framework(enum.Enum):
    DJANGO = "django"
    FAST_API = "fast_api"
    FLASK = "flask"
    TORNADO = "tornado"


class HeaderKey(enum.Enum):
    AUTHORIZATION = "Authorization"
    CONTENT_TYPE = "Content-Type"
    ENV = "X-Inngest-Env"
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
    SYNC_ID = "deployId"


class InternalEvents(enum.Enum):
    FUNCTION_FAILED = "inngest/function.failed"


class ServerKind(enum.Enum):
    CLOUD = "cloud"
    DEV_SERVER = "dev"
