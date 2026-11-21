"""Ordering items (lists now, cards in phase 3) with float positions.

The naive approach (positions 0, 1, 2, ...) means moving one item renumbers
every item after it. Instead positions have gaps (1024, 2048, 3072, ...) and an
item moved between two others takes the midpoint, so a move updates one row:

    A=1024  B=2048  C=3072      move C between A and B →  C=1536

Each midpoint halves the gap, so after ~50 moves into the same spot a float
runs out of precision. When the gap gets too small we renumber the siblings
once (`spread`) and try again.

`position_at` and `spread` are pure (numbers in, numbers out), so they're trivial
to test. `place` applies them to anything with a `position` attribute.
"""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.orm import Mapped


class Positioned(Protocol):
    """Any model with a float `position` column: BoardList and Card both qualify, without inheriting
    from this. That's structural typing — the type checker accepts any object with the right shape.

    Why `Mapped[float]` and not `float`: on SQLAlchemy models, `position` is declared as a
    `Mapped[float]` descriptor that *returns* a float when read on an instance. Type checkers
    compare the declared types, and `Mapped[float]` is not `float`, so the protocol states the
    shape models actually have.
    """

    position: Mapped[float]


GAP = 1024.0
MIN_GAP = 1e-6


def position_at(positions: list[float], index: int) -> float | None:
    """The position for a new item inserted at `index` of `positions` (sorted ascending).

    Returns None when there's no room between the neighbours: renumber with `spread` and retry.
    """
    if not 0 <= index <= len(positions):
        raise IndexError(f"index {index} out of range for {len(positions)} items")
    before = positions[index - 1] if index > 0 else None
    after = positions[index] if index < len(positions) else None

    if before is None and after is None:
        return GAP
    if before is None:
        return after - GAP  # type: ignore[operator]  # Negative positions are fine.
    if after is None:
        return before + GAP
    if after - before < MIN_GAP:
        return None
    return (before + after) / 2


def spread(count: int) -> list[float]:
    """Evenly spaced positions for `count` items: GAP, 2*GAP, ..."""
    return [GAP * (i + 1) for i in range(count)]


def place(siblings: Sequence[Positioned], index: int) -> float:
    """A position at `index` among `siblings` (sorted, not including the item being placed).

    If there's no room, the siblings are renumbered in place first (the caller commits).
    """
    position = position_at([s.position for s in siblings], index)
    if position is None:
        for sibling, new_position in zip(siblings, spread(len(siblings))):
            sibling.position = new_position
        position = position_at([s.position for s in siblings], index)
        assert position is not None  # A freshly spread sequence always has room.
    return position


def index_after(sibling_ids: list[int], after_id: int | None) -> int:
    """Where "right after `after_id`" lands (None = first). Raises ValueError for an unknown id."""
    if after_id is None:
        return 0
    return sibling_ids.index(after_id) + 1
