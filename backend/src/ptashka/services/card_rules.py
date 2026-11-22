"""Pure business rules about cards: plain values in, plain values out.

No session, no clock (`now` is a parameter), no HTTP, so they're unit-tested exhaustively in
microseconds (tests/test_card_rules.py), while the services that apply them stay thin shells:
load, decide (here), save. "Functional core, imperative shell".
"""

from datetime import datetime


def completion_after_move(
    completed_at: datetime | None,
    *,
    from_done: bool,
    to_done: bool,
    same_list: bool,
    now: datetime,
) -> datetime | None:
    """A card's `completed_at` after a move, by the done-list rule.

    Moving into the done list completes the card, keeping the original time if it was already
    completed; moving out of it reopens the card. Reordering within a list, or moving between
    ordinary lists, leaves completion alone (a card ticked as completed in "Doing" stays so).
    """
    if same_list or not (from_done or to_done):
        return completed_at
    if to_done:
        return completed_at or now
    return None
