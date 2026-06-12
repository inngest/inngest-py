import typing

from inngest._internal import server_lib

from . import base

_TEST_NAME = base.create_test_name(__file__)


def create_cases(framework: server_lib.Framework) -> list[base.Case]:
    return [
        base.Case(
            name=f"{_TEST_NAME}_patch_with_missing_auth",
            run_test=_patch_with_missing_auth(framework),
        ),
        base.Case(
            name=f"{_TEST_NAME}_patch_with_valid_auth",
            run_test=_patch_with_valid_auth(framework),
        ),
    ]


def _patch_with_missing_auth(
    framework: server_lib.Framework,
) -> typing.Callable[[base.TestCase], None]:
    def run_test(self: base.TestCase) -> None:
        base.serve_app(
            self,
            framework,
            is_production=True,
            name=f"{_TEST_NAME}-patch-with-missing-auth",
        )

        res = base.run_patch(self)

        base.assert_unsupported_method_response(res)

    return run_test


def _patch_with_valid_auth(
    framework: server_lib.Framework,
) -> typing.Callable[[base.TestCase], None]:
    def run_test(self: base.TestCase) -> None:
        base.serve_app(
            self,
            framework,
            is_production=True,
            name=f"{_TEST_NAME}-patch-with-valid-auth",
        )

        res = base.run_patch(self, signing_key=base.SIGNING_KEY)

        base.assert_unsupported_method_response(res)

    return run_test
