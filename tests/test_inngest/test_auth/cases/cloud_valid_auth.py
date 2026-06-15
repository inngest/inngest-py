import http
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
            name=f"{_TEST_NAME}_post",
            run_test=_post(framework),
        ),
        base.Case(
            name=f"{_TEST_NAME}_put_with_in_band",
            run_test=_put_in_band(framework),
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

        res = base.run_get(self, signing_key=base.SIGNING_KEY)

        assert res.status_code == http.HTTPStatus.OK
        base.assert_sdk_handled_response(res)

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
            signing_key=base.SIGNING_KEY,
        )

        assert res.status_code == http.HTTPStatus.OK
        base.assert_sdk_handled_response(res)

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

        res = base.run_in_band_put(self, signing_key=base.SIGNING_KEY)

        assert res.status_code == http.HTTPStatus.OK
        base.assert_sdk_handled_response(res)

    return run_test
