import hashlib
import re


from .types import T


def hash_signing_key(key: str) -> str:
    prefix_match = re.match(r"^signkey-[\w]+-", key)
    prefix = ""
    if prefix_match:
        prefix = prefix_match.group(0)

    key_without_prefix = key[len(prefix) :]
    hasher = hashlib.sha256()
    hasher.update(bytearray.fromhex(key_without_prefix))
    return hasher.hexdigest()


def hash_step_id(step_id: str, count: int) -> str:
    """
    Args:
        count: Number of times this step ID has been seen in the run.
    """

    if count > 1:
        step_id += f":{count}"

    # hasher = hashlib.sha1()
    # hasher.update(step_id.encode("utf-8"))
    # return hasher
    return hashlib.sha1(step_id.encode("utf-8")).hexdigest()


def remove_none_deep(obj: T) -> T:
    if isinstance(obj, dict):
        return {k: remove_none_deep(v) for k, v in obj.items() if v is not None}  # type: ignore
    if isinstance(obj, list):
        return [remove_none_deep(v) for v in obj if v is not None]  # type: ignore
    return obj
