from typing_extensions import assert_type

from . import types


class Test_is_dict:
    def test_dict(self) -> None:
        v: dict[object, object] = {}
        assert types.is_dict(v)
        assert_type(v, dict[object, object])

    def test_dict_with_key_type(self) -> None:
        v: dict[object, object] = {"a": 1}
        assert types.is_dict(v, str)
        assert_type(v, dict[str, object])

    def test_dict_with_key_type_invalid(self) -> None:
        v: dict[object, object] = {1: "a"}
        assert types.is_dict(v, str) is False

    def test_non_dicts(self) -> None:
        assert types.is_dict([]) is False
        assert types.is_dict("string") is False
        assert types.is_dict(123) is False
        assert types.is_dict(None) is False
        assert types.is_dict(set[str]()) is False
        assert types.is_dict(tuple[str]()) is False


class Test_is_list:
    def test_list(self) -> None:
        v: list[object] = []
        assert types.is_list(v)
        assert_type(v, list[object])

    def test_list_with_item_type_primitive(self) -> None:
        v: list[object] = ["a"]
        assert types.is_list(v, str)
        assert_type(v, list[str])

    def test_list_with_item_type_object(self) -> None:
        class Foo:
            pass

        v: list[Foo] = []
        assert types.is_list(v, Foo)
        assert_type(v, list[Foo])

    def test_list_with_item_type_invalid(self) -> None:
        v: list[object] = [1]
        assert types.is_list(v, str) is False

    def test_non_lists(self) -> None:
        assert types.is_list({}) is False
        assert types.is_list("string") is False
        assert types.is_list(123) is False
        assert types.is_list(None) is False
        assert types.is_list(set[str]()) is False
        assert types.is_list(tuple[str]()) is False
