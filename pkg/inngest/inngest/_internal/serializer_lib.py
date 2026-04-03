import typing

import pydantic


class Serializer(typing.Protocol):
    def serialize(self, obj: object, typ: object) -> object:
        """
        Serialize a Python object to a JSON object (dict, list, None, etc.).
        """
        ...

    def deserialize(self, obj: object, typ: object) -> object:
        """
        Deserialize a JSON object (dict, list, None, etc.).

        Args:
        ----
            obj: Python JSON object (dict, list, None, etc.).
            typ: Python type to deserialize into.
        """

        # NOTE: It'd be awesome to use a generic type signature like this:
        # def deserialize(self, obj: object, typ: type[T]) -> T:
        #     ...
        #
        # But this doesn't work with primitive types (int, str, etc.). We need
        # type[T] for classes but you can't pass primitives to type.
        ...


class PydanticSerializer(Serializer):
    def __init__(self) -> None:
        # TypeAdapter registers types in Pydantic's internal global registry on
        # every instantiation, and those entries are never freed. Caching
        # prevents unbounded memory growth in long-running workers.
        self._cache: dict[object, pydantic.TypeAdapter[object]] = {}

    def _get_adapter(self, typ: object) -> pydantic.TypeAdapter[object]:
        try:
            adapter = self._cache.get(typ)
        except TypeError:
            return pydantic.TypeAdapter(typ)
        if adapter is None:
            adapter = pydantic.TypeAdapter(typ)
            self._cache[typ] = adapter
        return adapter

    def serialize(self, obj: object, typ: object) -> object:
        """
        Serialize a Pydantic object to a JSON object (dict, list, None, etc.).
        """

        return self._get_adapter(typ).dump_python(obj, mode="json")

    def deserialize(self, obj: object, typ: object) -> object:
        """
        Deserialize a JSON object (dict, list, None, etc.) into a Pydantic
        object.
        """

        return self._get_adapter(typ).validate_python(obj)
