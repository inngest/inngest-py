from .buffer import _SizeConstrainedBuffer


def test_evict_oldest_items() -> None:
    """
    When eviction is necessary to make room for a new item, the oldest items
    are evicted.
    """

    buffer = _SizeConstrainedBuffer(3)

    # Fill the buffer with 3 items (each is 1 byte).
    assert buffer.add("1", b"A") is True
    assert buffer.get("1") is not None
    assert buffer.add("2", b"A") is True
    assert buffer.get("2") is not None
    assert buffer.add("3", b"A") is True
    assert buffer.get("3") is not None

    # Add a 2-byte item, which necessitates eviction.
    assert buffer.add("4", b"A" * 2) is True

    # The oldest 2 pre-existing items were evicted.
    assert buffer.get("1") is None
    assert buffer.get("2") is None

    # The most recent pre-existing item wasn't evicted.
    assert buffer.get("3") is not None

    # The new item was added.
    assert buffer.get("4") is not None


def test_item_larger_than_max_size() -> None:
    """
    If an item is larger than the max size, it is not added to the buffer.
    """

    buffer = _SizeConstrainedBuffer(1)

    assert buffer.add("1", b"A" * 2) is False
    assert buffer.get("1") is None
