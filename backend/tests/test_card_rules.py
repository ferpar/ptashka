"""Unit tests for services/card_rules.py: the done-list rule, every case, no database."""

from datetime import datetime, timezone

import pytest

from ptashka.services.card_rules import completion_after_move

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
EARLIER = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)

ORDINARY, DONE = False, True

# move                                       from      to        same list  completed before  completed after
CASES = [
    ("ordinary → done list",                 ORDINARY, DONE,     False,     None,             NOW),
    ("ordinary → done, already completed",   ORDINARY, DONE,     False,     EARLIER,          EARLIER),  # Keeps when it happened.
    ("done list → ordinary",                 DONE,     ORDINARY, False,     EARLIER,          None),     # Reopened.
    ("ordinary → ordinary",                  ORDINARY, ORDINARY, False,     None,             None),
    ("ordinary → ordinary, completed",       ORDINARY, ORDINARY, False,     EARLIER,          EARLIER),  # Ticked in "Doing": stays.
    ("reorder within the done list",         DONE,     DONE,     True,      EARLIER,          EARLIER),
    ("reorder within an ordinary list",      ORDINARY, ORDINARY, True,      None,             None),
]


@pytest.mark.parametrize("from_done, to_done, same_list, before, after", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_completion_after_move(from_done, to_done, same_list, before, after):
    assert completion_after_move(before, from_done=from_done, to_done=to_done, same_list=same_list, now=NOW) == after
