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
            name=f"{_TEST_NAME}_put",
            run_test=_put(framework),
        ),
    ]


def _get(
    framework: server_lib.Framework,
) -> typing.Callable[[base.TestCase], None]:
    def run_test(self: base.TestCase) -> None:
        base.serve_app(
            self,
            framework,
            is_production=False,
            name=f"{_TEST_NAME}-get",
        )

        res = base.run_get(self)

        assert res.status_code == http.HTTPStatus.OK
        base.assert_not_unauthorized(res)

    return run_test


def _post(
    framework: server_lib.Framework,
) -> typing.Callable[[base.TestCase], None]:
    def run_test(self: base.TestCase) -> None:
        app = base.serve_app(
            self,
            framework,
            is_production=False,
            name=f"{_TEST_NAME}-post",
        )

        res = base.run_post(self, fn_id=app.fn_id)

        assert res.status_code == http.HTTPStatus.OK
        base.assert_not_unauthorized(res)

    return run_test


def _put(
    framework: server_lib.Framework,
) -> typing.Callable[[base.TestCase], None]:
    def run_test(self: base.TestCase) -> None:
        mock_cloud = base.start_mock_cloud(self)
        base.serve_app(
            self,
            framework,
            is_production=False,
            mock_cloud=mock_cloud,
            name=f"{_TEST_NAME}-put",
        )

        res = base.run_out_of_band_put(self)

        base.assert_out_of_band_sync_succeeded(res, mock_cloud)

    return run_test
