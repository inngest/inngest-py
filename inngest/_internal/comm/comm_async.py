from __future__ import annotations

from inngest._internal import (
    const,
    errors,
    execution,
    function,
    net,
    transforms,
)

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

            # Look for the function ID in the list of user functions, but also
            # look for it in the list of on_failure functions.
            fn: function.Function | None = None
            for _fn in self._fns.values():
                if _fn.get_id() == fn_id:
                    fn = _fn
                    break
                if _fn.on_failure_fn_id == fn_id:
                    fn = _fn
                    break

            if fn is None:
                raise errors.MissingFunction(f"function {fn_id} not found")

            comm_res = base.CommResponse(
                headers={
                    **net.create_headers(framework=self._framework),
                    const.HeaderKey.SERVER_TIMING.value: "handler",
                }
            )

            action_res = await fn.call(call, self._client, fn_id)
            if isinstance(action_res, list):
                out: list[dict[str, object]] = []
                for item in action_res:
                    out.append(item.to_dict())

                comm_res.body = transforms.prep_body(out)
                comm_res.status_code = 206
            elif isinstance(action_res, execution.CallError):
                comm_res.body = transforms.prep_body(action_res.model_dump())
                comm_res.status_code = 500

                if action_res.is_retriable is False:
                    comm_res.headers[const.HeaderKey.NO_RETRY.value] = "true"
            else:
                comm_res.body = action_res

            return comm_res
        except errors.InternalError as err:
            body = {
                "code": str(err),
                "message": str(err),
            }
            self._logger.error(
                "function call failed",
                extra=body,
            )
            return base.CommResponse(
                body=body,
                headers=net.create_headers(framework=self._framework),
                status_code=err.status_code,
            )
