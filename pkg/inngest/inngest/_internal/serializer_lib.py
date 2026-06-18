import collections
import threading
import typing

import pydantic

_PYDANTIC_CACHE_MAX_SIZE = 512


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
        self._adapter_cache = _PydanticTypeAdapterCache(
            _PYDANTIC_CACHE_MAX_SIZE
        )

    def _get_adapter(self, typ: object) -> pydantic.TypeAdapter[object]:
        return self._adapter_cache.get(typ)

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


class _PydanticTypeAdapterCache:
    """
    Necessary because TypeAdapter registers types in Pydantic's internal global
    registry on every instantiation, and those entries are never freed. Bounded
    caching prevents repeated adapter creation for common stable types without
    strongly retaining arbitrary runtime-generated types forever.
    """

    def __init__(self, max_size: int) -> None:
        self._items: collections.OrderedDict[
            typing.Hashable,
            _PydanticTypeAdapterCacheItem,
        ] = collections.OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def get(self, typ: object) -> pydantic.TypeAdapter[object]:
        key = self._get_key(typ)
        with self._lock:
            item = self._items.get(key)
            if item is None:
                item = _PydanticTypeAdapterCacheItem(
                    adapter=pydantic.TypeAdapter(typ),
                    typ=typ,
                )
                self._items[key] = item
                if len(self._items) > self._max_size:
                    self._items.popitem(last=False)
            else:
                self._items.move_to_end(key)
            return item.adapter

    def _get_key(self, typ: object) -> typing.Hashable:
        try:
            # Ensure that typ is hashable
            hash(typ)
            return typing.cast(typing.Hashable, typ)
        except TypeError:
            # This is reachable for typing objects that include unhashable
            # metadata, e.g. `Annotated[int, {"key": "value"}]`.
            #
            # The identity key is safe for cache correctness because each cache
            # item stores the original type object while the entry is present,
            # so Python cannot reuse that object ID for a different type before
            # this cache entry is evicted.
            return ("id", id(typ))


class _PydanticTypeAdapterCacheItem(typing.NamedTuple):
    adapter: pydantic.TypeAdapter[object]

    # Only purpose is to keep a strong ref to TypeAdapter's underlying type.
    # This protects against the possibility of TypeAdapter intentionally losing
    # its strong reference to cause the underlying type to garbage collect.
    #
    # Preventing GC is important because we're effectively maintaining a mapping
    # of `typ -> TypeAdapter(typ)`. If the `typ` ever GCs then its id will
    # change, causing our _get_key fallback (the id(typ) based key) to be
    # incorrect
    typ: object
