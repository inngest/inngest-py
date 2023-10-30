from __future__ import annotations

from inngest._internal import errors, execution, function, net

from . import base


class CommHandlerSync(base.CommHandlerBase[function.FunctionSync]):
    """
    Synchronous version of CommHandler.
    """

    def call_function(
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
            return self._create_response(fn.call(call, self._client, fn_id))
        except errors.InternalError as err:
            return self._convert_error_to_response(err)
