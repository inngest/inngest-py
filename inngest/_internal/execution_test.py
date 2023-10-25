from .execution import CallResponse, Opcode


def test_serialization() -> None:
    actual = CallResponse(
        data={},
        display_name="my_display_name",
        id="my_id",
        name="my_name",
        op=Opcode.STEP,
        opts={},
    ).to_dict()

    expectation = {
        "data": {},
        "displayName": "my_display_name",
        "id": "my_id",
        "name": "my_name",
        "op": "Step",
        "opts": {},
    }

    assert actual == expectation
