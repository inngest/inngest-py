from inngest._internal import types


def get_nested(d: dict[object, object], key: str) -> object:
    # Get a nested value using a dot-separated key
    keys = key.split(".")
    for i, k in enumerate(keys):
        value = d[k]

        if i == len(keys) - 1:
            return value

        if not types.is_dict(value):
            raise TypeError(f"expected dict, got {type(value)}")

        d = value

    raise Exception("unreachable")
