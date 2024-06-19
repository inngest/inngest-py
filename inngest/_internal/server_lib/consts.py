import enum
import typing


class DeployType(enum.Enum):
    PING = "ping"


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
    RETRY_AFTER_ERROR = "retry_after_error"
    SERVER_KIND_MISMATCH = "server_kind_mismatch"
    SIGNING_KEY_UNSPECIFIED = "signing_key_unspecified"
    SIG_VERIFICATION_FAILED = "sig_verification_failed"
    STEP_ERRORED = "step_errored"
    STEP_UNEXPECTED = "step_unexpected"
    UNKNOWN = "unknown"
    URL_INVALID = "url_invalid"


class ExecutionVersion(enum.Enum):
    V0 = "0"
    V1 = "1"


PREFERRED_EXECUTION_VERSION: typing.Final = ExecutionVersion.V1.value


class Framework(enum.Enum):
    DIGITAL_OCEAN = "digitalocean"
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
    REQUEST_VERSION = "X-Inngest-Req-Version"
    RETRY_AFTER = "Retry-After"
    SDK = "X-Inngest-SDK"
    SERVER_KIND = "X-Inngest-Server-Kind"
    SERVER_TIMING = "Server-Timing"
    SIGNATURE = "X-Inngest-Signature"
    USER_AGENT = "User-Agent"


class InternalEvents(enum.Enum):
    FUNCTION_FAILED = "inngest/function.failed"


class Opcode(enum.Enum):
    INVOKE = "InvokeFunction"
    PLANNED = "StepPlanned"
    SLEEP = "Sleep"
    STEP_RUN = "StepRun"
    STEP_ERROR = "StepError"
    WAIT_FOR_EVENT = "WaitForEvent"


class QueryParamKey(enum.Enum):
    FUNCTION_ID = "fnId"
    STEP_ID = "stepId"
    SYNC_ID = "deployId"


class ServerKind(enum.Enum):
    CLOUD = "cloud"
    DEV_SERVER = "dev"


# If the Server sends this step ID then it isn't targeting a specific step
UNSPECIFIED_STEP_ID: typing.Final = "step"

ROOT_STEP_ID: typing.Final = "step"
