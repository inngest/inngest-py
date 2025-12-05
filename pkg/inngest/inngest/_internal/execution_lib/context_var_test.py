import unittest.mock

import pytest

from . import get_step_context, set_step_context, step


class TestContextVar:
    def test_set_and_get(self) -> None:
        step = unittest.mock.Mock()
        with set_step_context(step):
            assert get_step_context() == step

    def test_get_outside_with(self) -> None:
        step = unittest.mock.Mock()
        with set_step_context(step):
            pass

        with pytest.raises(LookupError):
            get_step_context()

    def test_set_without_with(self) -> None:
        step = unittest.mock.Mock()
        set_step_context(step)

        with pytest.raises(LookupError):
            get_step_context()

    def test_get_without_set(self) -> None:
        with pytest.raises(LookupError):
            get_step_context()

    def test_nested_set(self) -> None:
        with set_step_context(unittest.mock.Mock()):
            with pytest.raises(Exception) as e:
                with set_step_context(unittest.mock.Mock()):
                    pass
            assert str(e.value) == "Step context already set"


class TestStepDecorator:
    def test_can_call_outside_of_step_context(self) -> None:
        """
        If the step context is not set, the decorator is effectively a no-op (it
        just calls the decorated function directly)
        """

        @step("my-step")
        def my_step(name: str) -> str:
            return f"Hello {name}"

        assert my_step("Alice") == "Hello Alice"
