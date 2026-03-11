import datetime

from . import transforms


def test_hash_signing_key() -> None:
    signing_key = "signkey-prod-568c4116828e6e8384a554153722df93022e5cd29a6c2d1b0444a19a807ff315"
    expectation = (
        "2e64ca0edc850db32ff684f967822c828f99cf57862e43205fdcf2eff8d95180"
    )
    assert transforms.hash_signing_key(signing_key) == expectation


def test_to_duration_str() -> None:
    # Exact units
    assert transforms.to_duration_str(1000) == "1s"
    assert transforms.to_duration_str(datetime.timedelta(seconds=1)) == "1s"
    assert transforms.to_duration_str(datetime.timedelta(seconds=30)) == "30s"
    assert transforms.to_duration_str(datetime.timedelta(minutes=2)) == "2m"
    assert transforms.to_duration_str(datetime.timedelta(hours=2)) == "2h"
    assert transforms.to_duration_str(datetime.timedelta(days=3)) == "3d"
    assert transforms.to_duration_str(datetime.timedelta(weeks=2)) == "2w"

    # Non-exact-unit durations must not truncate
    assert transforms.to_duration_str(datetime.timedelta(seconds=90)) == "90s"
    assert transforms.to_duration_str(datetime.timedelta(minutes=90)) == "90m"
    assert transforms.to_duration_str(datetime.timedelta(hours=36)) == "36h"
    assert transforms.to_duration_str(datetime.timedelta(days=10)) == "10d"
    assert (
        transforms.to_duration_str(datetime.timedelta(minutes=2, seconds=30))
        == "150s"
    )

    # Sub-second durations are errors
    result = transforms.to_duration_str(datetime.timedelta(milliseconds=500))
    assert isinstance(result, Exception)
