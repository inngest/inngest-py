import pytest

# Make `assert` calls display a useful diff when they fail. Without this,
# `assert` failures just show "AssertionError" with no helpful diff.
pytest.register_assert_rewrite("test_inngest")
pytest.register_assert_rewrite("test_inngest_encryption")
