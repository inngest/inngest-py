import hashlib
import hmac
import json
from time import time

import pytest

from . import const, errors, net


def test_success() -> None:
    body = json.dumps({"msg": "hi"}).encode("utf-8")
    signing_key = "super-secret"
    unix_ms = round(time() * 1000)
    sig = _sign(body, signing_key, unix_ms)
    headers = {
        const.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
    }

    req_sig = net.RequestSignature(body, headers, is_production=True)
    req_sig.validate(signing_key)


def test_body_tamper() -> None:
    body = json.dumps({"msg": "bar"}).encode("utf-8")
    signing_key = "super-secret"
    unix_ms = round(time() * 1000)
    sig = _sign(body, signing_key, unix_ms)
    headers = {
        const.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
    }

    body = json.dumps({"msg": "you've been hacked"}).encode("utf-8")
    req_sig = net.RequestSignature(body, headers, is_production=True)

    with pytest.raises(errors.InvalidRequestSignature):
        req_sig.validate(signing_key)


def _sign(body: bytes, signing_key: str, unix_ms: int) -> str:
    mac = hmac.new(
        signing_key.encode("utf-8"),
        body,
        hashlib.sha256,
    )
    mac.update(str(unix_ms).encode("utf-8"))
    return mac.hexdigest()
