import collections
import dataclasses
import time


@dataclasses.dataclass
class _BufferItem:
    data: bytes
    id: str
    timestamp: float


class _SizeConstrainedBuffer:
    def __init__(self, max_size_bytes: int):
        """
        A size-constrained buffer. The total size of all items' data never
        exceeds the max size.
        """

        self._current_size = 0
        self._items: collections.OrderedDict[str, _BufferItem] = (
            collections.OrderedDict()
        )

        self._max_size_bytes = max_size_bytes
        if self._max_size_bytes <= 0:
            raise ValueError("max_size_bytes must be greater than 0")

    def add(self, item_id: str, data: bytes) -> bool:
        """
        Add item to buffer. If adding would exceed size limit, evicts oldest
        items until there is enough space. Returns True if item was added
        successfully. If the item is larger than the max size, it is not added
        to the buffer.
        """

        item_size = len(data)

        if item_size > self._max_size_bytes:
            return False

        # Remove existing item with same ID if it exists.
        if item_id in self._items:
            self._current_size -= len(self._items[item_id].data)
            del self._items[item_id]

        # If adding would exceed limit, evict oldest items until there's enough
        # space.
        while (
            self._current_size + item_size > self._max_size_bytes
            and self._items
        ):
            # Remove oldest item.
            _, oldest_item = self._items.popitem(last=False)
            self._current_size -= len(oldest_item.data)

        # Add new item.
        item = _BufferItem(
            data=data,
            id=item_id,
            timestamp=time.time(),
        )
        self._items[item_id] = item
        self._current_size += item_size
        return True

    def get(self, item_id: str) -> bytes | None:
        """
        Get item by ID without removing it.
        """

        item = self._items.get(item_id)
        if item is None:
            return None
        return item.data

    def delete(self, item_id: str) -> bool:
        """
        Delete item by ID. Returns True if item was found and deleted.
        """

        if item_id not in self._items:
            return False

        item = self._items[item_id]
        self._current_size -= len(item.data)
        del self._items[item_id]
        return True

    def get_older_than(self, seconds: float) -> list[tuple[str, bytes]]:
        """
        Get all items that were inserted at least `seconds` ago.
        """

        cutoff_time = time.time() - seconds
        result = []

        for item in self._items.values():
            if item.timestamp <= cutoff_time:
                result.append((item.id, item.data))

        return result
