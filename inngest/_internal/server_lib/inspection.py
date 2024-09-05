import typing

from inngest._internal import const, types

from .consts import ServerKind


class Capabilities(types.BaseModel):
    in_band_sync: str = "v1"
    trust_probe: str = "v1"


class UnauthenticatedInspection(types.BaseModel):
    schema_version: str = "2024-05-24"

    authentication_succeeded: typing.Optional[bool]
    function_count: int
    has_event_key: bool
    has_signing_key: bool
    has_signing_key_fallback: bool
    mode: ServerKind


class AuthenticatedInspection(UnauthenticatedInspection):
    api_origin: str
    app_id: str
    authentication_succeeded: bool = True
    capabilities: Capabilities = Capabilities()
    env: typing.Optional[str]
    event_api_origin: str
    event_key_hash: typing.Optional[str]
    framework: str
    sdk_language: str = const.LANGUAGE
    sdk_version: str = const.VERSION
    serve_origin: typing.Optional[str]
    serve_path: typing.Optional[str]
    signing_key_fallback_hash: typing.Optional[str]
    signing_key_hash: typing.Optional[str]
