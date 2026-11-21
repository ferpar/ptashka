"""The activity log: what gets recorded, what doesn't, and the two ways to read it."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from ptashka.api import cards as cards_api
from ptashka.main import app
from ptashka.services import activity_service
from tests.conftest import auth_headers
from tests.test_boards import add_member, create_board
from tests.test_cards import add_card, lists_by_name, move


@pytest.fixture(autouse=True)
def no_settle_delay(monkeypatch):
    """Entries normally reach the `since` feed after a few seconds; tests don't wait (except the
    one that checks the delay itself)."""
    monkeypatch.setattr(activity_service, "SETTLE", timedelta(0))


def history(client, user, board, **params):
    """Board activity, oldest first, as (kind, data) pairs."""
    response = client.get(f"/api/boards/{board['id']}/activity", params={"limit": 200, **params}, headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return [(a["kind"], a["data"]) for a in reversed(response.json()["activities"])]


def kinds(client, user, board):
    return [kind for kind, _ in history(client, user, board)]


# ── What gets recorded ──


def test_a_card_moved_to_done(client, user):
    board = create_board(client, user)
    ids = lists_by_name(board)
    card = add_card(client, user, ids["To do"], "Ship it")
    move(client, user, card, ids["Done"])

    entries = history(client, user, board)
    assert [k for k, _ in entries] == ["board.created", "card.created", "card.moved", "card.completed"]
    moved = entries[2][1]
    assert moved == {"card_title": "Ship it", "from_list_id": ids["To do"], "from_list": "To do",
                     "to_list_id": ids["Done"], "to_list": "Done"}

    raw = client.get(f"/api/boards/{board['id']}/activity", headers=auth_headers(user)).json()["activities"][0]
    assert raw["actor"]["id"] == user.id and raw["card_id"] == card["id"]


def test_card_updates_record_what_changed(client, user):
    board = create_board(client, user)
    card = add_card(client, user, lists_by_name(board)["To do"], "Draft", description="old")
    client.patch(f"/api/cards/{card['id']}", json={"title": "Final", "description": "new"}, headers=auth_headers(user))

    kind, data = history(client, user, board)[-1]
    assert kind == "card.updated"
    assert data["changed"] == ["description", "title"]
    # Short fields get old → new; long text is only noted as changed.
    assert data["from"] == {"title": "Draft"} and data["to"] == {"title": "Final"}


def test_board_list_and_member_changes(client, make_user, user):
    friend = make_user(email="friend@example.com")
    board = create_board(client, user)
    ids = lists_by_name(board)
    h = auth_headers(user)

    client.patch(f"/api/boards/{board['id']}", json={"name": "Family"}, headers=h)  # (Was "Home".)
    add_member(client, user, board["id"], friend.email, role="viewer")
    client.patch(f"/api/boards/{board['id']}/members/{friend.id}", json={"role": "contributor"}, headers=h)
    client.post(f"/api/boards/{board['id']}/lists", json={"name": "Later"}, headers=h)
    client.patch(f"/api/lists/{ids['Doing']}", json={"name": "In progress"}, headers=h)
    client.post(f"/api/lists/{ids['Done']}/move", json={"after_id": None}, headers=h)
    client.patch(f"/api/lists/{ids['Doing']}", json={"is_done": True}, headers=h)
    client.patch(f"/api/lists/{ids['To do']}", json={"archived": True}, headers=h)
    client.delete(f"/api/boards/{board['id']}/members/{friend.id}", headers=auth_headers(friend))  # Leaves.
    client.patch(f"/api/boards/{board['id']}", json={"archived": True}, headers=h)

    entries = history(client, user, board)
    assert [k for k, _ in entries] == [
        "board.created", "board.updated", "member.added", "member.role_changed", "list.created",
        "list.updated", "list.moved", "list.set_done", "list.archived", "member.removed", "board.archived",
    ]
    data = dict(entries)
    assert data["board.updated"]["from"] == {"name": "Home"} and data["board.updated"]["to"] == {"name": "Family"}
    assert (data["member.role_changed"]["from_role"], data["member.role_changed"]["to_role"]) == ("viewer", "contributor")
    assert data["member.removed"]["left"] is True


def test_card_details_are_recorded(client, make_user, user):
    friend = make_user(email="friend@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], friend.email)
    card = add_card(client, user, lists_by_name(board)["To do"], "Task")
    label = client.post(f"/api/boards/{board['id']}/labels", json={"name": "bug", "color": "red"}, headers=auth_headers(user)).json()
    h = auth_headers(user)

    client.put(f"/api/cards/{card['id']}/labels/{label['id']}", headers=h)
    client.delete(f"/api/cards/{card['id']}/labels/{label['id']}", headers=h)
    client.put(f"/api/cards/{card['id']}/assignees/{friend.id}", headers=h)
    client.delete(f"/api/cards/{card['id']}/assignees/{friend.id}", headers=h)
    item = client.post(f"/api/cards/{card['id']}/checklist", json={"text": "step"}, headers=h).json()
    client.patch(f"/api/checklist-items/{item['id']}", json={"done": True}, headers=h)
    client.patch(f"/api/checklist-items/{item['id']}", json={"done": False}, headers=h)
    client.post(f"/api/cards/{card['id']}/comments", json={"body": "x" * 500}, headers=h)

    entries = history(client, user, board)
    entries = entries[[k for k, _ in entries].index("card.created") + 1 :]  # What happened after the card existed.
    assert [k for k, _ in entries] == [
        "label.added", "label.removed", "assignee.added", "assignee.removed",
        "checklist.added", "checklist.checked", "checklist.unchecked", "comment.added",
    ]
    data = dict(entries)
    assert data["label.added"]["label_name"] == "bug"
    assert data["assignee.added"]["user_name"] == "friend"
    assert len(data["comment.added"]["excerpt"]) == activity_service_excerpt_length()


def activity_service_excerpt_length():
    from ptashka.services.comment_service import EXCERPT_LENGTH

    return EXCERPT_LENGTH


def test_deleted_cards_keep_their_history(client, user):
    board = create_board(client, user)
    card = add_card(client, user, lists_by_name(board)["To do"], "Doomed")
    client.patch(f"/api/cards/{card['id']}", json={"archived": True}, headers=auth_headers(user))
    client.delete(f"/api/cards/{card['id']}", headers=auth_headers(user))

    raw = client.get(f"/api/boards/{board['id']}/activity", headers=auth_headers(user)).json()["activities"]
    assert [(a["kind"], a["card_id"], a["data"]["card_title"]) for a in raw[:3]] == [
        ("card.deleted", None, "Doomed"),
        ("card.archived", None, "Doomed"),  # card_id was SET NULL when the card went; the title remains.
        ("card.created", None, "Doomed"),
    ]


# ── What doesn't get recorded ──


def test_no_ops_are_not_news(client, user):
    board = create_board(client, user)
    ids = lists_by_name(board)
    a = add_card(client, user, ids["To do"], "a")
    b = add_card(client, user, ids["To do"], "b")
    label = client.post(f"/api/boards/{board['id']}/labels", json={"name": "bug", "color": "red"}, headers=auth_headers(user)).json()
    h = auth_headers(user)
    before = kinds(client, user, board)

    client.patch(f"/api/cards/{a['id']}", json={"title": "a"}, headers=h)  # Same title.
    client.put(f"/api/cards/{a['id']}/labels/{label['id']}", headers=h)
    client.put(f"/api/cards/{a['id']}/labels/{label['id']}", headers=h)  # Already there.
    client.patch(f"/api/cards/{a['id']}", json={"completed": True}, headers=h)
    client.patch(f"/api/cards/{a['id']}", json={"completed": True}, headers=h)  # Already completed.
    move(client, user, a, ids["To do"], after=b)  # Reordering within a list.

    assert kinds(client, user, board)[len(before):] == ["label.added", "card.completed"]


def test_refused_requests_leave_no_trace(client, make_user, user):
    contributor = make_user(email="contributor@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], contributor.email, role="contributor")
    card = add_card(client, user, lists_by_name(board)["To do"], "Task")
    before = kinds(client, user, board)

    client.patch(f"/api/cards/{card['id']}", json={"title": "x"}, headers=auth_headers(contributor))  # 403
    client.patch(f"/api/cards/{card['id']}", json={"title": "x", "version": 99}, headers=auth_headers(user))  # 409
    assert kinds(client, user, board) == before


def test_a_failed_request_rolls_back_its_activity_too(client, user, monkeypatch):
    """The unit of work at work: the change and its record are one transaction."""
    board = create_board(client, user)
    card = add_card(client, user, lists_by_name(board)["To do"], "Task")
    before = kinds(client, user, board)

    monkeypatch.setattr(cards_api, "card_detail", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    response = TestClient(app, raise_server_exceptions=False).patch(
        f"/api/cards/{card['id']}", json={"title": "Changed"}, headers=auth_headers(user)
    )
    assert response.status_code == 500
    monkeypatch.undo()
    assert kinds(client, user, board) == before


# ── Reading: history pages ──


def test_history_pages_backwards_without_gaps_or_overlaps(client, user):
    board = create_board(client, user)
    todo = lists_by_name(board)["To do"]
    for i in range(7):
        add_card(client, user, todo, f"card {i}")  # 1 board.created + 7 card.created = 8 entries.

    seen, before = [], None
    while True:
        params = {"limit": 3, **({"before": before} if before else {})}
        page = client.get(f"/api/boards/{board['id']}/activity", params=params, headers=auth_headers(user)).json()
        seen += [a["id"] for a in page["activities"]]
        before = page["next_before"]
        if before is None:
            break
    assert len(seen) == 8 and seen == sorted(seen, reverse=True) and len(set(seen)) == 8


def test_card_history(client, user):
    board = create_board(client, user)
    ids = lists_by_name(board)
    card = add_card(client, user, ids["To do"], "Mine")
    add_card(client, user, ids["To do"], "Other")
    move(client, user, card, ids["Doing"])

    raw = client.get(f"/api/cards/{card['id']}/activity", headers=auth_headers(user)).json()["activities"]
    assert [a["kind"] for a in raw] == ["card.moved", "card.created"]


def test_history_permissions(client, make_user, user):
    viewer = make_user(email="viewer@example.com")
    outsider = make_user(email="outsider@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], viewer.email, role="viewer")

    assert client.get(f"/api/boards/{board['id']}/activity", headers=auth_headers(viewer)).status_code == 200
    assert client.get(f"/api/boards/{board['id']}/activity", headers=auth_headers(outsider)).status_code == 404


# ── Reading: the `since` feed (for polling agents) ──


def test_feed_returns_what_is_new_across_my_boards_only(client, make_user, user):
    stranger = make_user(email="stranger@example.com")
    mine_a = create_board(client, user, name="A")
    mine_b = create_board(client, user, name="B")
    create_board(client, stranger, name="Not mine")
    h = auth_headers(user)

    first = client.get("/api/activity", headers=h).json()
    assert {(a["kind"], a["data"]["name"]) for a in first["activities"]} == {("board.created", "A"), ("board.created", "B")}

    # Nothing new: same cursor back.
    again = client.get("/api/activity", params={"since": first["next_since"]}, headers=h).json()
    assert again == {"activities": [], "next_since": first["next_since"]}

    add_card(client, user, lists_by_name(mine_b)["To do"], "New task")
    add_card(client, stranger, lists_by_name(create_board(client, stranger))["To do"], "Their task")
    new = client.get("/api/activity", params={"since": first["next_since"]}, headers=h).json()
    assert [(a["kind"], a["board_id"]) for a in new["activities"]] == [("card.created", mine_b["id"])]
    assert mine_a  # (A is in the first batch above.)


def test_feed_waits_for_entries_to_settle(client, user, monkeypatch):
    """With the real delay, a just-recorded entry isn't in the feed yet; a transaction that took
    a moment to commit can't be skipped by a poller that already moved past a later id."""
    monkeypatch.setattr(activity_service, "SETTLE", timedelta(seconds=5))
    create_board(client, user)
    assert client.get("/api/activity", headers=auth_headers(user)).json()["activities"] == []

    monkeypatch.setattr(activity_service, "SETTLE", timedelta(0))
    assert len(client.get("/api/activity", headers=auth_headers(user)).json()["activities"]) == 1
