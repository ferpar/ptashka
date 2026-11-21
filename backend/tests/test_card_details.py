"""Labels, assignees, checklist items and comments."""

import pytest
from sqlalchemy.exc import IntegrityError

from ptashka.models.db import CardAssignee, CardLabel
from tests.conftest import auth_headers
from tests.test_boards import add_member, create_board
from tests.test_cards import add_card, lists_by_name


@pytest.fixture
def board(client, user):
    return create_board(client, user)


@pytest.fixture
def card(client, user, board):
    return add_card(client, user, lists_by_name(board)["To do"], "Card")


def get_card(client, user, card):
    return client.get(f"/api/cards/{card['id']}", headers=auth_headers(user)).json()


def board_card(client, user, board, card):
    """The card as it appears in the board view (with counts)."""
    detail = client.get(f"/api/boards/{board['id']}", headers=auth_headers(user)).json()
    return next(c for lst in detail["lists"] for c in lst["cards"] if c["id"] == card["id"])


def new_label(client, user, board, name="urgent", color="red"):
    response = client.post(f"/api/boards/{board['id']}/labels", json={"name": name, "color": color}, headers=auth_headers(user))
    assert response.status_code == 201, response.text
    return response.json()


# ── Labels ──


def test_board_labels_crud(client, user, board):
    label = new_label(client, user, board)
    assert client.get(f"/api/boards/{board['id']}", headers=auth_headers(user)).json()["labels"] == [label]

    # Names are unique per board...
    response = client.post(f"/api/boards/{board['id']}/labels", json={"name": "urgent", "color": "blue"}, headers=auth_headers(user))
    assert response.status_code == 409
    # ...but another board can reuse them.
    other = create_board(client, user, name="Other")
    new_label(client, user, other)

    renamed = client.patch(f"/api/labels/{label['id']}", json={"color": "purple"}, headers=auth_headers(user)).json()
    assert (renamed["name"], renamed["color"]) == ("urgent", "purple")
    assert client.post(f"/api/boards/{board['id']}/labels", json={"name": "x", "color": "magenta"}, headers=auth_headers(user)).status_code == 422


def test_attach_and_detach_labels_idempotently(client, user, board, card):
    label = new_label(client, user, board)
    url = f"/api/cards/{card['id']}/labels/{label['id']}"

    assert client.put(url, headers=auth_headers(user)).status_code == 204
    assert client.put(url, headers=auth_headers(user)).status_code == 204  # Again: still one label.
    assert get_card(client, user, card)["label_ids"] == [label["id"]]

    assert client.delete(url, headers=auth_headers(user)).status_code == 204
    assert client.delete(url, headers=auth_headers(user)).status_code == 204  # Already gone: fine.
    assert get_card(client, user, card)["label_ids"] == []


def test_deleting_a_label_removes_it_from_cards(client, user, board, card):
    label = new_label(client, user, board)
    client.put(f"/api/cards/{card['id']}/labels/{label['id']}", headers=auth_headers(user))
    assert client.delete(f"/api/labels/{label['id']}", headers=auth_headers(user)).status_code == 204
    assert get_card(client, user, card)["label_ids"] == []


def test_cannot_use_a_label_from_another_board(client, user, card):
    foreign = new_label(client, user, create_board(client, user, name="Other"))
    response = client.put(f"/api/cards/{card['id']}/labels/{foreign['id']}", headers=auth_headers(user))
    assert response.status_code == 422


def test_database_rejects_label_from_another_board(db_session, client, user, card):
    foreign = new_label(client, user, create_board(client, user, name="Other"))
    # Bypassing the service: lie about the board, either way it must fail.
    db_session.add(CardLabel(card_id=card["id"], label_id=foreign["id"], board_id=card["board_id"]))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# ── Assignees ──


def test_assign_members_idempotently(client, make_user, user, board, card):
    friend = make_user(email="friend@example.com")
    add_member(client, user, board["id"], friend.email, role="viewer")  # Any role can be assigned.
    url = f"/api/cards/{card['id']}/assignees/{friend.id}"

    assert client.put(url, headers=auth_headers(user)).status_code == 204
    assert client.put(url, headers=auth_headers(user)).status_code == 204
    assert get_card(client, user, card)["assignee_ids"] == [friend.id]
    assert client.delete(url, headers=auth_headers(user)).status_code == 204
    assert get_card(client, user, card)["assignee_ids"] == []


def test_only_members_can_be_assigned(client, make_user, user, card):
    stranger = make_user(email="stranger@example.com")
    response = client.put(f"/api/cards/{card['id']}/assignees/{stranger.id}", headers=auth_headers(user))
    assert response.status_code == 422
    assert client.put(f"/api/cards/{card['id']}/assignees/99999", headers=auth_headers(user)).status_code == 422


def test_leaving_a_board_removes_your_assignments(client, make_user, user, board, card):
    """No code does this: the foreign key to board_members cascades."""
    friend = make_user(email="friend@example.com")
    add_member(client, user, board["id"], friend.email)
    client.put(f"/api/cards/{card['id']}/assignees/{friend.id}", headers=auth_headers(user))

    client.delete(f"/api/boards/{board['id']}/members/{friend.id}", headers=auth_headers(friend))
    assert get_card(client, user, card)["assignee_ids"] == []


def test_database_rejects_non_member_assignee(db_session, make_user, card):
    stranger = make_user(email="stranger@example.com")
    db_session.add(CardAssignee(card_id=card["id"], user_id=stranger.id, board_id=card["board_id"]))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# ── Checklist ──


def add_item(client, user, card, text):
    response = client.post(f"/api/cards/{card['id']}/checklist", json={"text": text}, headers=auth_headers(user))
    assert response.status_code == 201, response.text
    return response.json()


def test_checklist_order_and_counts(client, user, board, card):
    a, b, c = (add_item(client, user, card, t) for t in "abc")
    assert [i["text"] for i in get_card(client, user, card)["checklist"]] == ["a", "b", "c"]

    client.post(f"/api/checklist-items/{c['id']}/move", json={"after_id": None}, headers=auth_headers(user))
    assert [i["text"] for i in get_card(client, user, card)["checklist"]] == ["c", "a", "b"]

    done = client.patch(f"/api/checklist-items/{a['id']}", json={"done": True}, headers=auth_headers(user)).json()
    assert done["done_at"] is not None
    on_board = board_card(client, user, board, card)
    assert (on_board["checklist_done"], on_board["checklist_total"]) == (1, 3)

    assert client.delete(f"/api/checklist-items/{b['id']}", headers=auth_headers(user)).status_code == 204
    detail = get_card(client, user, card)
    assert (detail["checklist_done"], detail["checklist_total"]) == (1, 2)


def test_checklist_move_rejects_items_from_other_cards(client, user, board, card):
    other_card = add_card(client, user, lists_by_name(board)["To do"], "Other")
    mine = add_item(client, user, card, "mine")
    theirs = add_item(client, user, other_card, "theirs")
    response = client.post(f"/api/checklist-items/{mine['id']}/move", json={"after_id": theirs["id"]}, headers=auth_headers(user))
    assert response.status_code == 422


# ── Comments ──


def comment(client, author, card, body):
    response = client.post(f"/api/cards/{card['id']}/comments", json={"body": body}, headers=auth_headers(author))
    assert response.status_code == 201, response.text
    return response.json()


def test_comments_are_listed_oldest_first_with_authors(client, make_user, user, board, card):
    friend = make_user(email="friend@example.com")
    add_member(client, user, board["id"], friend.email)
    comment(client, user, card, "first")
    comment(client, friend, card, "second")

    listed = client.get(f"/api/cards/{card['id']}/comments", headers=auth_headers(user)).json()["comments"]
    assert [(c["body"], c["author"]["id"]) for c in listed] == [("first", user.id), ("second", friend.id)]
    assert board_card(client, user, board, card)["comment_count"] == 2


def test_only_the_author_edits(client, make_user, user, board, card):
    editor = make_user(email="editor@example.com")
    add_member(client, user, board["id"], editor.email)
    mine = comment(client, editor, card, "typo")
    url = f"/api/comments/{mine['id']}"

    edited = client.patch(url, json={"body": "fixed"}, headers=auth_headers(editor)).json()
    assert edited["body"] == "fixed" and edited["edited_at"] is not None
    # Not even the board owner can rewrite someone else's words.
    assert client.patch(url, json={"body": "hijacked"}, headers=auth_headers(user)).status_code == 403


def test_author_or_owner_deletes(client, make_user, user, board, card):
    a = make_user(email="a@example.com")
    b = make_user(email="b@example.com")
    for u in (a, b):
        add_member(client, user, board["id"], u.email)
    by_a = comment(client, a, card, "a's")
    by_a_too = comment(client, a, card, "a's again")

    assert client.delete(f"/api/comments/{by_a['id']}", headers=auth_headers(b)).status_code == 403
    assert client.delete(f"/api/comments/{by_a['id']}", headers=auth_headers(a)).status_code == 204
    assert client.delete(f"/api/comments/{by_a_too['id']}", headers=auth_headers(user)).status_code == 204  # Owner.


def test_viewers_read_but_do_not_comment(client, make_user, user, board, card):
    viewer = make_user(email="viewer@example.com")
    add_member(client, user, board["id"], viewer.email, role="viewer")
    comment(client, user, card, "hello")
    assert len(client.get(f"/api/cards/{card['id']}/comments", headers=auth_headers(viewer)).json()["comments"]) == 1
    response = client.post(f"/api/cards/{card['id']}/comments", json={"body": "hi"}, headers=auth_headers(viewer))
    assert response.status_code == 403


def test_comment_survives_author_account_deletion(client, db_session, make_user, user, board, card):
    friend = make_user(email="friend@example.com")
    add_member(client, user, board["id"], friend.email)
    comment(client, friend, card, "still here")
    db_session.delete(friend)
    db_session.commit()

    listed = client.get(f"/api/cards/{card['id']}/comments", headers=auth_headers(user)).json()["comments"]
    assert [(c["body"], c["author"]) for c in listed] == [("still here", None)]


# ── Permissions and deletion ──


def test_outsiders_get_404_on_every_detail_resource(client, make_user, user, board, card):
    outsider = make_user(email="outsider@example.com")
    label = new_label(client, user, board)
    item = add_item(client, user, card, "x")
    note = comment(client, user, card, "x")
    h = auth_headers(outsider)

    assert client.patch(f"/api/labels/{label['id']}", json={"color": "blue"}, headers=h).json()["detail"] == "Label not found"
    assert client.patch(f"/api/checklist-items/{item['id']}", json={"done": True}, headers=h).json()["detail"] == "Checklist item not found"
    assert client.delete(f"/api/comments/{note['id']}", headers=h).json()["detail"] == "Comment not found"
    assert client.get(f"/api/cards/{card['id']}/comments", headers=h).status_code == 404


def test_deleting_a_full_board_cascades(client, make_user, user, board, card):
    """With passive_deletes the database removes everything in one DELETE; nothing may be left behind."""
    friend = make_user(email="friend@example.com")
    add_member(client, user, board["id"], friend.email)
    label = new_label(client, user, board)
    client.put(f"/api/cards/{card['id']}/labels/{label['id']}", headers=auth_headers(user))
    client.put(f"/api/cards/{card['id']}/assignees/{friend.id}", headers=auth_headers(user))
    add_item(client, user, card, "x")
    comment(client, user, card, "x")

    assert client.delete(f"/api/boards/{board['id']}", headers=auth_headers(user)).status_code == 204
    assert client.get(f"/api/cards/{card['id']}", headers=auth_headers(user)).status_code == 404
