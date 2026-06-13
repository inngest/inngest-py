import typing

from inngest._internal import server_lib

from . import base

_TEST_NAME = base.create_test_name(__file__)


def create_cases(framework: server_lib.Framework) -> list[base.Case]:
    return [
        base.Case(
            name=f"{_TEST_NAME}_get",
            run_test=_get(framework),
        ),
        base.Case(
            name=f"{_TEST_NAME}_get_malformed_signature",
            run_test=_get_malformed_signature(framework),
        ),
        base.Case(
            name=f"{_TEST_NAME}_post",
            run_test=_post(framework),
        ),
        base.Case(
            name=f"{_TEST_NAME}_put_with_in_band",
            run_test=_put_in_band(framework),
        ),
        base.Case(
            name=f"{_TEST_NAME}_put_with_out_of_band_with_disable_option",
            run_test=_put_out_of_band_disable_option(framework),
        ),
    ]


def _get(
    framework: server_lib.Framework,
) -> typing.Callable[[base.TestCase], None]:
    def run_test(self: base.TestCase) -> None:
        base.serve_app(
            self,
            framework,
            is_production=True,
            name=f"{_TEST_NAME}-get",
        )

        res = base.run_get(self, signing_key=base.WRONG_SIGNING_KEY)

        base.assert_unauthorized_response(res)

    return run_test


def _get_malformed_signature(
    framework: server_lib.Framework,
) -> typing.Callable[[base.TestCase], None]:
    def run_test(self: base.TestCase) -> None:
        base.serve_app(
            self,
            framework,
            is_production=True,
            name=f"{_TEST_NAME}-get-malformed-signature",
        )

        res = self.get(
            headers={
                server_lib.HeaderKey.SIGNATURE.value: "t=bad&s=invalid",
            },
        )

        base.assert_unauthorized_response(res)

    return run_test


def _post(
    framework: server_lib.Framework,
) -> typing.Callable[[base.TestCase], None]:
    def run_test(self: base.TestCase) -> None:
        app = base.serve_app(
            self,
            framework,
            is_production=True,
            name=f"{_TEST_NAME}-post",
        )

        res = base.run_post(
            self,
            fn_id=app.fn_id,
            signing_key=base.WRONG_SIGNING_KEY,
        )

        base.assert_unauthorized_response(res)

    return run_test


def _put_in_band(
    framework: server_lib.Framework,
) -> typing.Callable[[base.TestCase], None]:
    def run_test(self: base.TestCase) -> None:
        base.serve_app(
            self,
            framework,
            is_production=True,
            name=f"{_TEST_NAME}-put-in-band",
        )

        res = base.run_in_band_put(self, signing_key=base.WRONG_SIGNING_KEY)

        base.assert_unauthorized_response(res)

    return run_test


def _put_out_of_band_disable_option(
    framework: server_lib.Framework,
) -> typing.Callable[[base.TestCase], None]:
    def run_test(self: base.TestCase) -> None:
        base.serve_app(
            self,
            framework,
            enable_unauthed_sync=False,
            is_production=True,
            name=f"{_TEST_NAME}-put-out-of-band-disable-option",
        )

        res = base.run_out_of_band_put(
            self,
            signing_key=base.WRONG_SIGNING_KEY,
        )

        base.assert_unauthorized_response(res)

    return run_test
