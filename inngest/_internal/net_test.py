import hashlib
import hmac
import json
import time

from . import const, errors, net


def test_success() -> None:
    body = json.dumps({"msg": "hi"}).encode("utf-8")
    signing_key = "super-secret"
    unix_ms = round(time.time() * 1000)
    sig = _sign(body, signing_key, unix_ms)
    headers = {
        const.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
    }

    req_sig = net.RequestSignature(body, headers, is_production=True)
    assert not isinstance(req_sig.validate(signing_key), Exception)


def test_body_tamper() -> None:
    body = json.dumps({"msg": "bar"}).encode("utf-8")
    signing_key = "super-secret"
    unix_ms = round(time.time() * 1000)
    sig = _sign(body, signing_key, unix_ms)
    headers = {
        const.HeaderKey.SIGNATURE.value: f"s={sig}&t={unix_ms}",
    }

    body = json.dumps({"msg": "you've been hacked"}).encode("utf-8")
    req_sig = net.RequestSignature(body, headers, is_production=True)

    validation = req_sig.validate(signing_key)
    assert isinstance(validation, errors.InvalidRequestSignatureError)


def _sign(body: bytes, signing_key: str, unix_ms: int) -> str:
    mac = hmac.new(
        signing_key.encode("utf-8"),
        body,
        hashlib.sha256,
    )
    mac.update(str(unix_ms).encode("utf-8"))
    return mac.hexdigest()
