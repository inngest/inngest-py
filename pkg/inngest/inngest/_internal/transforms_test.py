import datetime

from . import transforms


def test_hash_signing_key() -> None:
    signing_key = "signkey-prod-568c4116828e6e8384a554153722df93022e5cd29a6c2d1b0444a19a807ff315"
    expectation = (
        "2e64ca0edc850db32ff684f967822c828f99cf57862e43205fdcf2eff8d95180"
    )
    assert transforms.hash_signing_key(signing_key) == expectation


def test_to_duration_str() -> None:
    out = transforms.to_duration_str(1000)
    assert out == "1s"

    out = transforms.to_duration_str(datetime.timedelta(minutes=2))
    assert out == "2m"
