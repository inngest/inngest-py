from __future__ import annotations

import dataclasses
import typing
import urllib.parse

import httpx

from inngest._internal import (
    client_lib,
    const,
    errors,
    function,
    net,
    server_lib,
    transforms,
    types,
)


class AppSyncer:
    def __init__(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
        client: client_lib.Inngest,
        fns: list[function.Function],
        framework: server_lib.Framework,
        query_params: typing.Union[dict[str, str], dict[str, list[str]]],
        request_url: str,
        serve_origin: typing.Optional[str],
        serve_path: typing.Optional[str],
        signing_key: typing.Optional[str],
        signing_key_fallback: typing.Optional[str],
    ) -> None:
        self._body = body
        self._headers = headers
        self._client = client
        self._fns = fns
        self._framework = framework
        self._query_params = query_params

        server_kind = transforms.get_server_kind(self._headers)
        if isinstance(server_kind, Exception):
            self._client.logger.error(server_kind)
            server_kind = None
        self._request_server_kind = server_kind

        self._request_url = request_url
        self._serve_origin = serve_origin
        self._serve_path = serve_path
        self._signing_key = signing_key
        self._signing_key_fallback = signing_key_fallback

    def run(self) -> _SyncResponse:
        """Handle a registration call."""

        result: types.MaybeError[types.BaseModel]
        if self._request_server_kind is server_lib.ServerKind.CLOUD:
            result = self._run_in_band_flow()
        elif self._client._mode is server_lib.ServerKind.DEV_SERVER:
            result = self._run_legacy_flow()
        else:
            result = self._run_upgrade_flow()

        # # TODO: Handle signing key rotation
        return _SyncResponse(result=result, signing_key=self._signing_key)

    def _run_legacy_flow(
        self,
    ) -> types.MaybeError[server_lib.UnauthenticatedSyncResponse]:
        """
        Run the legacy flow where we send a sync request to the Inngest Server
        """

        # TODO: Replace this code when the Dev Server supports the new in-band
        # flow

        app_url = net.create_serve_url(
            request_url=self._request_url,
            serve_origin=self._serve_origin,
            serve_path=self._serve_path,
        )

        params = server_lib.parse_query_params(self._query_params)
        if isinstance(params, Exception):
            return params

        req = _build_register_request(
            api_origin=self._client._api_origin,
            app_url=app_url,
            client=self._client,
            fns=self._fns,
            framework=self._framework,
            server_kind=self._request_server_kind,
            sync_id=params.sync_id,
        )
        if isinstance(req, Exception):
            return req

        res = net.fetch_with_auth_fallback_sync(
            self._client._http_client_sync,
            req,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res

        try:
            server_res_body = res.json()
        except Exception:
            return errors.RegistrationFailedError("response is not valid JSON")

        if not isinstance(server_res_body, dict):
            return errors.RegistrationFailedError("response is not an object")

        if res.status_code >= 400:
            msg = server_res_body.get("error")
            if not isinstance(msg, str):
                msg = "registration failed"

            return errors.RegistrationFailedError(msg.strip())

        return server_lib.UnauthenticatedSyncResponse()

    def _run_in_band_flow(
        self,
    ) -> types.MaybeError[server_lib.AuthenticatedSyncResponse]:
        """
        Run the flow where we directly respond with the sync config
        """

        err = net.validate_request(
            body=self._body,
            headers=self._headers,
            mode=self._client._mode,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(err, Exception):
            return err

        parsed_body = server_lib.SyncRequest.from_raw(self._body)
        if isinstance(parsed_body, Exception):
            return parsed_body

        # Use the body instead of the request URL since the body is
        # trustworthy
        request_url = parsed_body.url

        app_url = net.create_serve_url(
            request_url=request_url,
            serve_origin=self._serve_origin,
            serve_path=self._serve_path,
        )

        fn_configs = _get_function_configs(app_url, self._fns)
        if isinstance(fn_configs, Exception):
            return fn_configs

        return server_lib.AuthenticatedSyncResponse(
            app_name=self._client.app_id,
            functions=fn_configs,
            deploy_type=server_lib.DeployType.PING,
            framework=self._framework,
            sdk=f"{const.LANGUAGE}:v{const.VERSION}",
            url=app_url,
            v="0.1",
        )

    def _run_upgrade_flow(
        self,
    ) -> types.MaybeError[server_lib.UnauthenticatedSyncResponse]:
        """
        Run the flow where we "upgrade" an unauthenticated sync request to an
        authenticated sync request. For example, this happens when a user uses
        curl to initiate a sync
        """

        # TODO: Implement. Need to send signed ping to Inngest Server

        return server_lib.UnauthenticatedSyncResponse()


def _build_register_request(
    *,
    api_origin: str,
    app_url: str,
    client: client_lib.Inngest,
    fns: list[function.Function],
    framework: server_lib.Framework,
    server_kind: typing.Optional[server_lib.ServerKind],
    sync_id: typing.Optional[str],
) -> types.MaybeError[httpx.Request]:
    registration_url = urllib.parse.urljoin(api_origin, "/fn/register")

    fn_configs = _get_function_configs(app_url, fns)
    if isinstance(fn_configs, Exception):
        return fn_configs

    body = server_lib.LegacySyncRequest(
        app_name=client.app_id,
        deploy_type=server_lib.DeployType.PING,
        framework=framework,
        functions=fn_configs,
        sdk=f"{const.LANGUAGE}:v{const.VERSION}",
        url=app_url,
        v="0.1",
    ).to_dict()
    if isinstance(body, Exception):
        return body

    headers = net.create_headers(
        env=client.env,
        framework=framework,
        server_kind=server_kind,
    )

    params = {}
    if sync_id is not None:
        params[server_lib.QueryParamKey.SYNC_ID.value] = sync_id

    return client._http_client_sync.build_request(
        "POST",
        registration_url,
        headers=headers,
        json=transforms.deep_strip_none(body),
        params=params,
        timeout=30,
    )


def _get_function_configs(
    app_url: str,
    fns: list[function.Function],
) -> types.MaybeError[list[server_lib.FunctionConfig]]:
    configs: list[server_lib.FunctionConfig] = []
    for fn in fns:
        config = fn.get_config(app_url)
        configs.append(config.main)

        if config.on_failure is not None:
            configs.append(config.on_failure)

    if len(configs) == 0:
        return errors.FunctionConfigInvalidError("no functions found")
    return configs


@dataclasses.dataclass
class _SyncResponse:
    result: types.MaybeError[types.BaseModel]
    signing_key: typing.Optional[str]
