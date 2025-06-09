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
    def serialize(self, obj: object, typ: object) -> object:
        """
        Serialize a Pydantic object to a JSON object (dict, list, None, etc.).
        """

        adapter = pydantic.TypeAdapter(object)
        return adapter.dump_python(obj, mode="json")

    def deserialize(self, obj: object, typ: object) -> object:
        """
        Deserialize a JSON object (dict, list, None, etc.) into a Pydantic
        object.
        """

        adapter = pydantic.TypeAdapter[object](typ)
        return adapter.validate_python(obj)
