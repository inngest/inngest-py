from __future__ import annotations

import httpx

from inngest._internal import errors, execution, function, net

from . import base


class CommHandler(base.CommHandlerBase[function.Function]):
    async def call_function(
        self,
        *,
        call: execution.Call,
        fn_id: str,
        req_sig: net.RequestSignature,
    ) -> base.CommResponse:
        """
        Handles a function call from the Executor.
        """

        try:
            req_sig.validate(self._signing_key)
            fn = self._get_function(fn_id)
            return self._create_response(
                await fn.call(call, self._client, fn_id)
            )
        except errors.InternalError as err:
            return base.CommResponse.from_internal_error(err, self._framework)

    async def register(
        self,
        *,
        app_url: str,
        is_from_dev_server: bool,
    ) -> base.CommResponse:
        """
        Handles a registration call.
        """

        try:
            self._validate_registration(is_from_dev_server)

            async with httpx.AsyncClient() as client:
                res = await client.send(
                    self._build_registration_request(app_url),
                )

            return self._parse_registration_response(res)
        except errors.InternalError as err:
            return base.CommResponse.from_internal_error(err, self._framework)
