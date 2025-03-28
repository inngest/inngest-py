import random
import string


def random_suffix(value: str) -> str:
    return f"{value}-{_random_string(16)}"


def _random_string(length: int) -> str:
    return "".join(
        random.choices(string.ascii_letters + string.digits, k=length)
    )
