"""Position management for columns and cards.

The invariant, everywhere: within one parent, positions are exactly the integers
0..n-1, with no gaps and no duplicates. Every function here restores that before
returning, and no caller is trusted to maintain it by hand.

The unique constraints backing this are DEFERRABLE INITIALLY DEFERRED, because
renumbering necessarily passes through states where two rows share a position.
They are checked once at commit, on the final arrangement.
"""

from typing import Protocol


class Positioned(Protocol):
    position: int


def renumber(items: list[Positioned]) -> None:
    """Assign 0..n-1 in list order, touching only rows whose position changed."""
    for index, item in enumerate(items):
        if item.position != index:
            item.position = index


def _without(items: list, item) -> list:
    # Compared by primary key rather than identity: the item may have been loaded
    # by a different query than the list it is being removed from.
    return [existing for existing in items if existing.id != item.id]


def insert_at(siblings: list, item, index: int) -> None:
    """Place item among siblings at index, then renumber.

    Siblings may or may not already contain item. The index is clamped, so a
    client asking for position 99 in a column of three lands at the end rather
    than creating a gap or an error.
    """
    remaining = _without(siblings, item)
    index = max(0, min(index, len(remaining)))
    remaining.insert(index, item)
    renumber(remaining)


def remove_from(siblings: list, item) -> None:
    """Close the gap left by removing item from its siblings."""
    renumber(_without(siblings, item))
