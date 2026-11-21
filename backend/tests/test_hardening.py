"""Data-integrity guarantees: the composite foreign key, the done list, and optimistic locking."""

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import set_committed_value

from ptashka.models.db import Board, BoardList, Card
from ptashka.services import card_service
from tests.conftest import auth_headers
from tests.test_boards import create_board
from tests.test_cards import add_card, lists_by_name, move


# ── Composite foreign key: card.board_id must match its list's board ──


def test_database_rejects_card_with_mismatched_board(db_session):
    board_a = Board(name="A")
    board_b = Board(name="B")
    db_session.add_all([board_a, board_b])
    db_session.flush()
    list_on_a = BoardList(board_id=board_a.id, name="L", position=1.0)
    db_session.add(list_on_a)
    db_session.flush()

    # Written directly, bypassing card_service: the database itself must refuse it.
    db_session.add(Card(list_id=list_on_a.id, board_id=board_b.id, title="Liar", position=1.0))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_moving_a_list_to_another_board_carries_its_cards(db_session, client, user):
    board = create_board(client, user)
    other = create_board(client, user, name="Other")
    todo = lists_by_name(board)["To do"]
    card = add_card(client, user, todo, "Travels along")

    # No API for this yet: ON UPDATE CASCADE is what would make it a one-line change.
    db_session.execute(update(BoardList).where(BoardList.id == todo).values(board_id=other["id"]))
    db_session.commit()
    assert db_session.get(Card, card["id"]).board_id == other["id"]


# ── Done list ──


def card_state(client, user, card):
    body = client.get(f"/api/cards/{card['id']}", headers=auth_headers(user)).json()
    return body["completed_at"]


def test_new_boards_have_done_as_the_done_list(client, user):
    board = create_board(client, user)
    assert {lst["name"]: lst["is_done"] for lst in board["lists"]} == {"To do": False, "Doing": False, "Done": True}


def test_moving_into_done_completes_and_moving_out_reopens(client, user):
    ids = lists_by_name(create_board(client, user))
    card = add_card(client, user, ids["To do"], "Task")

    move(client, user, card, ids["Doing"])
    assert card_state(client, user, card) is None  # Between ordinary lists: untouched.

    move(client, user, card, ids["Done"])
    completed_at = card_state(client, user, card)
    assert completed_at is not None

    done_twin = add_card(client, user, ids["Done"], "Already done")
    move(client, user, card, ids["Done"], after=done_twin)  # Reordering inside Done keeps the timestamp.
    assert card_state(client, user, card) == completed_at

    move(client, user, card, ids["To do"])
    assert card_state(client, user, card) is None


def test_card_created_in_done_list_is_completed(client, user):
    done = lists_by_name(create_board(client, user))["Done"]
    assert add_card(client, user, done, "Retroactive")["completed_at"] is not None


def test_completing_without_moving_still_works(client, user):
    """The done list is a shortcut, not the only way: agents can tick a card where it is."""
    todo = lists_by_name(create_board(client, user))["To do"]
    card = add_card(client, user, todo, "Quick win")
    body = client.patch(f"/api/cards/{card['id']}", json={"completed": True}, headers=auth_headers(user)).json()
    assert body["completed_at"] is not None and body["list_id"] == todo


def test_choosing_a_new_done_list_replaces_the_old_one(client, user):
    board = create_board(client, user)
    ids = lists_by_name(board)
    shipped = client.post(f"/api/boards/{board['id']}/lists", json={"name": "Shipped"}, headers=auth_headers(user)).json()

    response = client.patch(f"/api/lists/{shipped['id']}", json={"is_done": True}, headers=auth_headers(user))
    assert response.json()["is_done"] is True
    lists = client.get(f"/api/boards/{board['id']}", headers=auth_headers(user)).json()["lists"]
    assert [lst["name"] for lst in lists if lst["is_done"]] == ["Shipped"]

    # Moving into the old Done list no longer completes anything.
    card = add_card(client, user, ids["To do"], "Task")
    move(client, user, card, ids["Done"])
    assert card_state(client, user, card) is None


def test_database_allows_only_one_done_list_per_board(db_session):
    board = Board(name="B")
    db_session.add(board)
    db_session.flush()
    db_session.add_all([BoardList(board_id=board.id, name=n, position=p, is_done=True) for n, p in (("A", 1), ("B", 2))])
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# ── Optimistic locking ──


def patch(client, user, card, **body):
    return client.patch(f"/api/cards/{card['id']}", json=body, headers=auth_headers(user))


def test_version_increases_on_every_change(client, user):
    todo = lists_by_name(create_board(client, user))["To do"]
    card = add_card(client, user, todo, "v1")
    other = add_card(client, user, todo, "other")
    assert card["version"] == 1
    assert patch(client, user, card, title="v2").json()["version"] == 2
    assert move(client, user, card, todo, after=other).json()["version"] == 3  # Moves count as changes too.
    # A request that changes nothing sends no UPDATE, so the version stays put.
    assert move(client, user, card, todo, after=other).json()["version"] == 3


def test_stale_version_is_rejected_and_nothing_is_overwritten(client, user):
    """Two people open the card at version 1; the second save must not clobber the first."""
    todo = lists_by_name(create_board(client, user))["To do"]
    card = add_card(client, user, todo, "Original", description="Shared notes")

    first = patch(client, user, card, description="Alice's edit", version=1)
    assert first.status_code == 200

    second = patch(client, user, card, description="Bob's edit", version=1)
    assert second.status_code == 409
    assert second.json()["detail"]["current_version"] == 2
    assert client.get(f"/api/cards/{card['id']}", headers=auth_headers(user)).json()["description"] == "Alice's edit"

    # Bob reloads, sees version 2, and can save on top of it.
    assert patch(client, user, card, description="Bob's edit", version=2).status_code == 200


def test_without_version_last_write_wins(client, user):
    todo = lists_by_name(create_board(client, user))["To do"]
    card = add_card(client, user, todo, "x")
    patch(client, user, card, title="first")
    assert patch(client, user, card, title="second").json()["title"] == "second"


def test_race_between_check_and_write_is_caught(client, db_session, user):
    """The version matched when we checked, but someone committed before our UPDATE ran.
    SQLAlchemy's `WHERE version = N` catches it at flush time."""
    todo = lists_by_name(create_board(client, user))["To do"]
    created = add_card(client, user, todo, "Original")

    # The other request commits its change (version 1 → 2)...
    db_session.execute(update(Card).where(Card.id == created["id"]).values(title="Theirs", version=Card.version + 1))
    db_session.commit()
    # ...but our request read the card just *before* that commit, so its copy still says version 1.
    card = db_session.get(Card, created["id"])
    set_committed_value(card, "version", 1)

    # The early check passes (1 == 1); only the UPDATE ... WHERE version = 1 can catch it.
    with pytest.raises(card_service.VersionConflictError) as conflict:
        card_service.update_card(db_session, card, {"title": "Mine", "version": 1})
    assert conflict.value.current_version == 2
    db_session.expire_all()
    assert db_session.get(Card, card.id).title == "Theirs"  # Their committed write survives; ours was refused.
