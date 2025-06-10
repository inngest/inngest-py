from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GatewayMessageType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GATEWAY_HELLO: _ClassVar[GatewayMessageType]
    WORKER_CONNECT: _ClassVar[GatewayMessageType]
    GATEWAY_CONNECTION_READY: _ClassVar[GatewayMessageType]
    GATEWAY_EXECUTOR_REQUEST: _ClassVar[GatewayMessageType]
    WORKER_READY: _ClassVar[GatewayMessageType]
    WORKER_REQUEST_ACK: _ClassVar[GatewayMessageType]
    WORKER_REQUEST_EXTEND_LEASE: _ClassVar[GatewayMessageType]
    WORKER_REQUEST_EXTEND_LEASE_ACK: _ClassVar[GatewayMessageType]
    WORKER_REPLY: _ClassVar[GatewayMessageType]
    WORKER_REPLY_ACK: _ClassVar[GatewayMessageType]
    WORKER_PAUSE: _ClassVar[GatewayMessageType]
    WORKER_HEARTBEAT: _ClassVar[GatewayMessageType]
    GATEWAY_HEARTBEAT: _ClassVar[GatewayMessageType]
    GATEWAY_CLOSING: _ClassVar[GatewayMessageType]

class SDKResponseStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NOT_COMPLETED: _ClassVar[SDKResponseStatus]
    DONE: _ClassVar[SDKResponseStatus]
    ERROR: _ClassVar[SDKResponseStatus]

class ConnectionStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CONNECTED: _ClassVar[ConnectionStatus]
    READY: _ClassVar[ConnectionStatus]
    DRAINING: _ClassVar[ConnectionStatus]
    DISCONNECTING: _ClassVar[ConnectionStatus]
    DISCONNECTED: _ClassVar[ConnectionStatus]

class WorkerDisconnectReason(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WORKER_SHUTDOWN: _ClassVar[WorkerDisconnectReason]
    UNEXPECTED: _ClassVar[WorkerDisconnectReason]
    GATEWAY_DRAINING: _ClassVar[WorkerDisconnectReason]
    CONSECUTIVE_HEARTBEATS_MISSED: _ClassVar[WorkerDisconnectReason]
    MESSAGE_TOO_LARGE: _ClassVar[WorkerDisconnectReason]
GATEWAY_HELLO: GatewayMessageType
WORKER_CONNECT: GatewayMessageType
GATEWAY_CONNECTION_READY: GatewayMessageType
GATEWAY_EXECUTOR_REQUEST: GatewayMessageType
WORKER_READY: GatewayMessageType
WORKER_REQUEST_ACK: GatewayMessageType
WORKER_REQUEST_EXTEND_LEASE: GatewayMessageType
WORKER_REQUEST_EXTEND_LEASE_ACK: GatewayMessageType
WORKER_REPLY: GatewayMessageType
WORKER_REPLY_ACK: GatewayMessageType
WORKER_PAUSE: GatewayMessageType
WORKER_HEARTBEAT: GatewayMessageType
GATEWAY_HEARTBEAT: GatewayMessageType
GATEWAY_CLOSING: GatewayMessageType
NOT_COMPLETED: SDKResponseStatus
DONE: SDKResponseStatus
ERROR: SDKResponseStatus
CONNECTED: ConnectionStatus
READY: ConnectionStatus
DRAINING: ConnectionStatus
DISCONNECTING: ConnectionStatus
DISCONNECTED: ConnectionStatus
WORKER_SHUTDOWN: WorkerDisconnectReason
UNEXPECTED: WorkerDisconnectReason
GATEWAY_DRAINING: WorkerDisconnectReason
CONSECUTIVE_HEARTBEATS_MISSED: WorkerDisconnectReason
MESSAGE_TOO_LARGE: WorkerDisconnectReason

class ConnectMessage(_message.Message):
    __slots__ = ("kind", "payload")
    KIND_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    kind: GatewayMessageType
    payload: bytes
    def __init__(self, kind: _Optional[_Union[GatewayMessageType, str]] = ..., payload: _Optional[bytes] = ...) -> None: ...

class AppConfiguration(_message.Message):
    __slots__ = ("app_name", "app_version", "functions")
    APP_NAME_FIELD_NUMBER: _ClassVar[int]
    APP_VERSION_FIELD_NUMBER: _ClassVar[int]
    FUNCTIONS_FIELD_NUMBER: _ClassVar[int]
    app_name: str
    app_version: str
    functions: bytes
    def __init__(self, app_name: _Optional[str] = ..., app_version: _Optional[str] = ..., functions: _Optional[bytes] = ...) -> None: ...

class AuthData(_message.Message):
    __slots__ = ("session_token", "sync_token")
    SESSION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    SYNC_TOKEN_FIELD_NUMBER: _ClassVar[int]
    session_token: str
    sync_token: str
    def __init__(self, session_token: _Optional[str] = ..., sync_token: _Optional[str] = ...) -> None: ...

class WorkerConnectRequestData(_message.Message):
    __slots__ = ("connection_id", "instance_id", "auth_data", "capabilities", "apps", "worker_manual_readiness_ack", "system_attributes", "environment", "framework", "platform", "sdk_version", "sdk_language", "started_at")
    CONNECTION_ID_FIELD_NUMBER: _ClassVar[int]
    INSTANCE_ID_FIELD_NUMBER: _ClassVar[int]
    AUTH_DATA_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    APPS_FIELD_NUMBER: _ClassVar[int]
    WORKER_MANUAL_READINESS_ACK_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    FRAMEWORK_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    SDK_VERSION_FIELD_NUMBER: _ClassVar[int]
    SDK_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    connection_id: str
    instance_id: str
    auth_data: AuthData
    capabilities: bytes
    apps: _containers.RepeatedCompositeFieldContainer[AppConfiguration]
    worker_manual_readiness_ack: bool
    system_attributes: SystemAttributes
    environment: str
    framework: str
    platform: str
    sdk_version: str
    sdk_language: str
    started_at: _timestamp_pb2.Timestamp
    def __init__(self, connection_id: _Optional[str] = ..., instance_id: _Optional[str] = ..., auth_data: _Optional[_Union[AuthData, _Mapping]] = ..., capabilities: _Optional[bytes] = ..., apps: _Optional[_Iterable[_Union[AppConfiguration, _Mapping]]] = ..., worker_manual_readiness_ack: bool = ..., system_attributes: _Optional[_Union[SystemAttributes, _Mapping]] = ..., environment: _Optional[str] = ..., framework: _Optional[str] = ..., platform: _Optional[str] = ..., sdk_version: _Optional[str] = ..., sdk_language: _Optional[str] = ..., started_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class GatewayConnectionReadyData(_message.Message):
    __slots__ = ("heartbeat_interval", "extend_lease_interval")
    HEARTBEAT_INTERVAL_FIELD_NUMBER: _ClassVar[int]
    EXTEND_LEASE_INTERVAL_FIELD_NUMBER: _ClassVar[int]
    heartbeat_interval: str
    extend_lease_interval: str
    def __init__(self, heartbeat_interval: _Optional[str] = ..., extend_lease_interval: _Optional[str] = ...) -> None: ...

class GatewayExecutorRequestData(_message.Message):
    __slots__ = ("request_id", "account_id", "env_id", "app_id", "app_name", "function_id", "function_slug", "step_id", "request_payload", "system_trace_ctx", "user_trace_ctx", "run_id", "lease_id")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    ENV_ID_FIELD_NUMBER: _ClassVar[int]
    APP_ID_FIELD_NUMBER: _ClassVar[int]
    APP_NAME_FIELD_NUMBER: _ClassVar[int]
    FUNCTION_ID_FIELD_NUMBER: _ClassVar[int]
    FUNCTION_SLUG_FIELD_NUMBER: _ClassVar[int]
    STEP_ID_FIELD_NUMBER: _ClassVar[int]
    REQUEST_PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_TRACE_CTX_FIELD_NUMBER: _ClassVar[int]
    USER_TRACE_CTX_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    LEASE_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    account_id: str
    env_id: str
    app_id: str
    app_name: str
    function_id: str
    function_slug: str
    step_id: str
    request_payload: bytes
    system_trace_ctx: bytes
    user_trace_ctx: bytes
    run_id: str
    lease_id: str
    def __init__(self, request_id: _Optional[str] = ..., account_id: _Optional[str] = ..., env_id: _Optional[str] = ..., app_id: _Optional[str] = ..., app_name: _Optional[str] = ..., function_id: _Optional[str] = ..., function_slug: _Optional[str] = ..., step_id: _Optional[str] = ..., request_payload: _Optional[bytes] = ..., system_trace_ctx: _Optional[bytes] = ..., user_trace_ctx: _Optional[bytes] = ..., run_id: _Optional[str] = ..., lease_id: _Optional[str] = ...) -> None: ...

class WorkerRequestAckData(_message.Message):
    __slots__ = ("request_id", "account_id", "env_id", "app_id", "function_slug", "step_id", "system_trace_ctx", "user_trace_ctx", "run_id")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    ENV_ID_FIELD_NUMBER: _ClassVar[int]
    APP_ID_FIELD_NUMBER: _ClassVar[int]
    FUNCTION_SLUG_FIELD_NUMBER: _ClassVar[int]
    STEP_ID_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_TRACE_CTX_FIELD_NUMBER: _ClassVar[int]
    USER_TRACE_CTX_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    account_id: str
    env_id: str
    app_id: str
    function_slug: str
    step_id: str
    system_trace_ctx: bytes
    user_trace_ctx: bytes
    run_id: str
    def __init__(self, request_id: _Optional[str] = ..., account_id: _Optional[str] = ..., env_id: _Optional[str] = ..., app_id: _Optional[str] = ..., function_slug: _Optional[str] = ..., step_id: _Optional[str] = ..., system_trace_ctx: _Optional[bytes] = ..., user_trace_ctx: _Optional[bytes] = ..., run_id: _Optional[str] = ...) -> None: ...

class WorkerRequestExtendLeaseData(_message.Message):
    __slots__ = ("request_id", "account_id", "env_id", "app_id", "function_slug", "step_id", "system_trace_ctx", "user_trace_ctx", "run_id", "lease_id")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    ENV_ID_FIELD_NUMBER: _ClassVar[int]
    APP_ID_FIELD_NUMBER: _ClassVar[int]
    FUNCTION_SLUG_FIELD_NUMBER: _ClassVar[int]
    STEP_ID_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_TRACE_CTX_FIELD_NUMBER: _ClassVar[int]
    USER_TRACE_CTX_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    LEASE_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    account_id: str
    env_id: str
    app_id: str
    function_slug: str
    step_id: str
    system_trace_ctx: bytes
    user_trace_ctx: bytes
    run_id: str
    lease_id: str
    def __init__(self, request_id: _Optional[str] = ..., account_id: _Optional[str] = ..., env_id: _Optional[str] = ..., app_id: _Optional[str] = ..., function_slug: _Optional[str] = ..., step_id: _Optional[str] = ..., system_trace_ctx: _Optional[bytes] = ..., user_trace_ctx: _Optional[bytes] = ..., run_id: _Optional[str] = ..., lease_id: _Optional[str] = ...) -> None: ...

class WorkerRequestExtendLeaseAckData(_message.Message):
    __slots__ = ("request_id", "account_id", "env_id", "app_id", "function_slug", "new_lease_id")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    ENV_ID_FIELD_NUMBER: _ClassVar[int]
    APP_ID_FIELD_NUMBER: _ClassVar[int]
    FUNCTION_SLUG_FIELD_NUMBER: _ClassVar[int]
    NEW_LEASE_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    account_id: str
    env_id: str
    app_id: str
    function_slug: str
    new_lease_id: str
    def __init__(self, request_id: _Optional[str] = ..., account_id: _Optional[str] = ..., env_id: _Optional[str] = ..., app_id: _Optional[str] = ..., function_slug: _Optional[str] = ..., new_lease_id: _Optional[str] = ...) -> None: ...

class SDKResponse(_message.Message):
    __slots__ = ("request_id", "account_id", "env_id", "app_id", "status", "body", "no_retry", "retry_after", "sdk_version", "request_version", "system_trace_ctx", "user_trace_ctx", "run_id")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    ENV_ID_FIELD_NUMBER: _ClassVar[int]
    APP_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    NO_RETRY_FIELD_NUMBER: _ClassVar[int]
    RETRY_AFTER_FIELD_NUMBER: _ClassVar[int]
    SDK_VERSION_FIELD_NUMBER: _ClassVar[int]
    REQUEST_VERSION_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_TRACE_CTX_FIELD_NUMBER: _ClassVar[int]
    USER_TRACE_CTX_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    account_id: str
    env_id: str
    app_id: str
    status: SDKResponseStatus
    body: bytes
    no_retry: bool
    retry_after: str
    sdk_version: str
    request_version: int
    system_trace_ctx: bytes
    user_trace_ctx: bytes
    run_id: str
    def __init__(self, request_id: _Optional[str] = ..., account_id: _Optional[str] = ..., env_id: _Optional[str] = ..., app_id: _Optional[str] = ..., status: _Optional[_Union[SDKResponseStatus, str]] = ..., body: _Optional[bytes] = ..., no_retry: bool = ..., retry_after: _Optional[str] = ..., sdk_version: _Optional[str] = ..., request_version: _Optional[int] = ..., system_trace_ctx: _Optional[bytes] = ..., user_trace_ctx: _Optional[bytes] = ..., run_id: _Optional[str] = ...) -> None: ...

class WorkerReplyAckData(_message.Message):
    __slots__ = ("request_id",)
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    def __init__(self, request_id: _Optional[str] = ...) -> None: ...

class ConnMetadata(_message.Message):
    __slots__ = ("id", "gateway_id", "instance_id", "all_worker_groups", "synced_worker_groups", "status", "last_heartbeat_at", "sdk_language", "sdk_version", "attributes")
    class AllWorkerGroupsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    class SyncedWorkerGroupsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_ID_FIELD_NUMBER: _ClassVar[int]
    INSTANCE_ID_FIELD_NUMBER: _ClassVar[int]
    ALL_WORKER_GROUPS_FIELD_NUMBER: _ClassVar[int]
    SYNCED_WORKER_GROUPS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    LAST_HEARTBEAT_AT_FIELD_NUMBER: _ClassVar[int]
    SDK_LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    SDK_VERSION_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    id: str
    gateway_id: str
    instance_id: str
    all_worker_groups: _containers.ScalarMap[str, str]
    synced_worker_groups: _containers.ScalarMap[str, str]
    status: ConnectionStatus
    last_heartbeat_at: _timestamp_pb2.Timestamp
    sdk_language: str
    sdk_version: str
    attributes: SystemAttributes
    def __init__(self, id: _Optional[str] = ..., gateway_id: _Optional[str] = ..., instance_id: _Optional[str] = ..., all_worker_groups: _Optional[_Mapping[str, str]] = ..., synced_worker_groups: _Optional[_Mapping[str, str]] = ..., status: _Optional[_Union[ConnectionStatus, str]] = ..., last_heartbeat_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., sdk_language: _Optional[str] = ..., sdk_version: _Optional[str] = ..., attributes: _Optional[_Union[SystemAttributes, _Mapping]] = ...) -> None: ...

class SystemAttributes(_message.Message):
    __slots__ = ("cpu_cores", "mem_bytes", "os")
    CPU_CORES_FIELD_NUMBER: _ClassVar[int]
    MEM_BYTES_FIELD_NUMBER: _ClassVar[int]
    OS_FIELD_NUMBER: _ClassVar[int]
    cpu_cores: int
    mem_bytes: int
    os: str
    def __init__(self, cpu_cores: _Optional[int] = ..., mem_bytes: _Optional[int] = ..., os: _Optional[str] = ...) -> None: ...

class ConnGroup(_message.Message):
    __slots__ = ("env_id", "app_id", "app_name", "hash", "conns", "sync_id", "app_version")
    ENV_ID_FIELD_NUMBER: _ClassVar[int]
    APP_ID_FIELD_NUMBER: _ClassVar[int]
    APP_NAME_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    CONNS_FIELD_NUMBER: _ClassVar[int]
    SYNC_ID_FIELD_NUMBER: _ClassVar[int]
    APP_VERSION_FIELD_NUMBER: _ClassVar[int]
    env_id: str
    app_id: str
    app_name: str
    hash: str
    conns: _containers.RepeatedCompositeFieldContainer[ConnMetadata]
    sync_id: str
    app_version: str
    def __init__(self, env_id: _Optional[str] = ..., app_id: _Optional[str] = ..., app_name: _Optional[str] = ..., hash: _Optional[str] = ..., conns: _Optional[_Iterable[_Union[ConnMetadata, _Mapping]]] = ..., sync_id: _Optional[str] = ..., app_version: _Optional[str] = ...) -> None: ...

class StartResponse(_message.Message):
    __slots__ = ("connection_id", "gateway_endpoint", "gateway_group", "session_token", "sync_token")
    CONNECTION_ID_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_ENDPOINT_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_GROUP_FIELD_NUMBER: _ClassVar[int]
    SESSION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    SYNC_TOKEN_FIELD_NUMBER: _ClassVar[int]
    connection_id: str
    gateway_endpoint: str
    gateway_group: str
    session_token: str
    sync_token: str
    def __init__(self, connection_id: _Optional[str] = ..., gateway_endpoint: _Optional[str] = ..., gateway_group: _Optional[str] = ..., session_token: _Optional[str] = ..., sync_token: _Optional[str] = ...) -> None: ...

class StartRequest(_message.Message):
    __slots__ = ("exclude_gateways",)
    EXCLUDE_GATEWAYS_FIELD_NUMBER: _ClassVar[int]
    exclude_gateways: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, exclude_gateways: _Optional[_Iterable[str]] = ...) -> None: ...

class FlushResponse(_message.Message):
    __slots__ = ("request_id",)
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    def __init__(self, request_id: _Optional[str] = ...) -> None: ...

class PubSubAckMessage(_message.Message):
    __slots__ = ("ts", "nack", "nack_reason")
    TS_FIELD_NUMBER: _ClassVar[int]
    NACK_FIELD_NUMBER: _ClassVar[int]
    NACK_REASON_FIELD_NUMBER: _ClassVar[int]
    ts: _timestamp_pb2.Timestamp
    nack: bool
    nack_reason: SystemError
    def __init__(self, ts: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., nack: bool = ..., nack_reason: _Optional[_Union[SystemError, _Mapping]] = ...) -> None: ...

class SystemError(_message.Message):
    __slots__ = ("code", "data", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: str
    data: bytes
    message: str
    def __init__(self, code: _Optional[str] = ..., data: _Optional[bytes] = ..., message: _Optional[str] = ...) -> None: ...
