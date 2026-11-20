"""Unit tests for the pure ordering functions: no database, no HTTP."""

import pytest

from ptashka.services.ordering import GAP, position_at, spread


def test_first_item_gets_gap():
    assert position_at([], 0) == GAP


def test_insert_at_start_end_and_middle():
    positions = [1024.0, 2048.0]
    assert position_at(positions, 0) == 0.0  # before 1024
    assert position_at(positions, 2) == 3072.0  # after 2048
    assert position_at(positions, 1) == 1536.0  # midpoint


def test_repeated_midpoints_eventually_run_out_of_room():
    before, after = 1024.0, 2048.0
    for _ in range(100):
        middle = position_at([before, after], 1)
        if middle is None:
            break
        after = middle
    else:
        pytest.fail("expected the gap to collapse")
    # ...and spreading always restores room.
    assert position_at(spread(2), 1) == 1536.0


def test_index_out_of_range():
    with pytest.raises(IndexError):
        position_at([1.0], 5)
