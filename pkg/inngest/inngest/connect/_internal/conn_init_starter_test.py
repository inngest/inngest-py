import unittest

from .conn_init_starter import validate_gateway_endpoint


class Test_validate_gateway_endpoint(unittest.TestCase):
    def test_valid(self) -> None:
        assert validate_gateway_endpoint("ws://example.com") is None
        assert validate_gateway_endpoint("wss://example.com") is None

    def test_invalid(self) -> None:
        # Unsupported scheme
        err = validate_gateway_endpoint("http://example.com")
        assert isinstance(err, Exception)
        assert (
            str(err)
            == "gateway endpoint scheme http is not valid, must be one of ws, wss"
        )

        # Missing hostname
        err = validate_gateway_endpoint("ws://")
        assert isinstance(err, Exception)
        assert str(err) == "gateway endpoint hostname is required"

        # Empty (use spaces to also test stripping)
        err = validate_gateway_endpoint("  ")
        assert isinstance(err, Exception)
        assert str(err) == "gateway endpoint is empty"
