import datetime
import unittest

import pydantic

from inngest._internal.serializer_lib import PydanticSerializer


class _User(pydantic.BaseModel):
    name: str
    age: int


class _Address(pydantic.BaseModel):
    street: str
    city: str


class _Nested(pydantic.BaseModel):
    user: _User
    address: _Address


class TestPydanticSerializer_serialize(unittest.TestCase):
    def setUp(self) -> None:
        self.s = PydanticSerializer()

    def test_dict(self) -> None:
        result = self.s.serialize({"key": "value"}, object)
        assert result == {"key": "value"}

    def test_pydantic_model(self) -> None:
        user = _User(name="Alice", age=30)
        result = self.s.serialize(user, object)
        assert result == {"name": "Alice", "age": 30}

    def test_nested_model(self) -> None:
        obj = _Nested(
            user=_User(name="Alice", age=30),
            address=_Address(street="123 Main", city="Springfield"),
        )
        result = self.s.serialize(obj, object)
        assert result == {
            "user": {"name": "Alice", "age": 30},
            "address": {"street": "123 Main", "city": "Springfield"},
        }

    def test_list(self) -> None:
        result = self.s.serialize([1, 2, 3], object)
        assert result == [1, 2, 3]

    def test_none(self) -> None:
        result = self.s.serialize(None, object)
        assert result is None

    def test_primitive_str(self) -> None:
        result = self.s.serialize("hello", object)
        assert result == "hello"

    def test_primitive_int(self) -> None:
        result = self.s.serialize(42, object)
        assert result == 42

    def test_datetime_to_json(self) -> None:
        dt = datetime.datetime(
            2024, 1, 15, 12, 0, 0, tzinfo=datetime.timezone.utc
        )
        result = self.s.serialize(dt, object)
        assert isinstance(result, str)


class TestPydanticSerializer_deserialize(unittest.TestCase):
    def setUp(self) -> None:
        self.s = PydanticSerializer()

    def test_pydantic_model(self) -> None:
        result = self.s.deserialize({"name": "Alice", "age": 30}, _User)
        assert isinstance(result, _User)
        assert result.name == "Alice"
        assert result.age == 30

    def test_nested_model(self) -> None:
        data = {
            "user": {"name": "Alice", "age": 30},
            "address": {"street": "123 Main", "city": "Springfield"},
        }
        result = self.s.deserialize(data, _Nested)
        assert isinstance(result, _Nested)
        assert isinstance(result.user, _User)
        assert isinstance(result.address, _Address)

    def test_primitive_int(self) -> None:
        assert self.s.deserialize(42, int) == 42

    def test_primitive_str(self) -> None:
        assert self.s.deserialize("hello", str) == "hello"

    def test_primitive_bool(self) -> None:
        assert self.s.deserialize(True, bool) is True

    def test_list_of_ints(self) -> None:
        result = self.s.deserialize([1, 2, 3], list[int])
        assert result == [1, 2, 3]

    def test_dict_type(self) -> None:
        result = self.s.deserialize(
            {"a": 1, "b": 2},
            dict[str, int],
        )
        assert result == {"a": 1, "b": 2}

    def test_optional_with_value(self) -> None:
        assert self.s.deserialize(5, int | None) == 5

    def test_optional_with_none(self) -> None:
        assert self.s.deserialize(None, int | None) is None

    def test_list_of_models(self) -> None:
        data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        result = self.s.deserialize(data, list[_User])
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(u, _User) for u in result)

    def test_none_to_object(self) -> None:
        assert self.s.deserialize(None, object) is None


class TestPydanticSerializer_adapter_cache(unittest.TestCase):
    def setUp(self) -> None:
        self.s = PydanticSerializer()

    def test_same_class_returns_cached(self) -> None:
        a1 = self.s._get_adapter(_User)
        a2 = self.s._get_adapter(_User)
        assert a1 is a2

    def test_object_type_returns_cached(self) -> None:
        a1 = self.s._get_adapter(object)
        a2 = self.s._get_adapter(object)
        assert a1 is a2

    def test_generic_alias_returns_cached(self) -> None:
        a1 = self.s._get_adapter(list[int])
        a2 = self.s._get_adapter(list[int])
        assert a1 is a2

    def test_different_types_return_different_adapters(self) -> None:
        a1 = self.s._get_adapter(_User)
        a2 = self.s._get_adapter(_Address)
        assert a1 is not a2

    def test_different_instances_have_separate_caches(self) -> None:
        s1 = PydanticSerializer()
        s2 = PydanticSerializer()
        a1 = s1._get_adapter(_User)
        a2 = s2._get_adapter(_User)
        assert a1 is not a2


class TestPydanticSerializer_RoundTrip(unittest.TestCase):
    def setUp(self) -> None:
        self.s = PydanticSerializer()

    def test_pydantic_model(self) -> None:
        original = _User(name="Alice", age=30)
        serialized = self.s.serialize(original, object)
        deserialized = self.s.deserialize(serialized, _User)
        assert deserialized == original

    def test_nested_model(self) -> None:
        original = _Nested(
            user=_User(name="Alice", age=30),
            address=_Address(street="123 Main", city="Springfield"),
        )
        serialized = self.s.serialize(original, object)
        deserialized = self.s.deserialize(serialized, _Nested)
        assert deserialized == original

    def test_dict(self) -> None:
        original = {"key": "value", "count": 42}
        serialized = self.s.serialize(original, object)
        deserialized = self.s.deserialize(serialized, dict[str, object])
        assert deserialized == original
