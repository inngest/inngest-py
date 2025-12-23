import typing

from inngest._internal import const, types

from .consts import ServerKind


class Capabilities(types.BaseModel):
    connect: str = "v1"
    in_band_sync: str = "v1"
    trust_probe: str = "v1"


class UnauthenticatedInspection(types.BaseModel):
    schema_version: str = "2024-05-24"

    function_count: int
    has_event_key: bool
    has_signing_key: bool
    has_signing_key_fallback: bool
    mode: ServerKind


class AuthenticatedInspection(types.BaseModel):
    schema_version: str = "2024-05-24"

    api_origin: str
    app_id: str
    authentication_succeeded: typing.Literal[True] = True
    capabilities: Capabilities = Capabilities()
    env: str | None
    event_api_origin: str
    event_key_hash: str | None
    framework: str
    function_count: int
    has_event_key: bool
    has_signing_key: bool
    has_signing_key_fallback: bool
    mode: ServerKind
    sdk_language: str = const.LANGUAGE
    sdk_version: str = const.VERSION
    serve_origin: str | None
    serve_path: str | None
    signing_key_fallback_hash: str | None
    signing_key_hash: str | None
