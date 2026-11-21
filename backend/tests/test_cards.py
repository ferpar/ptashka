from datetime import datetime

from tests.conftest import auth_headers
from tests.test_boards import add_member, create_board


def lists_by_name(board):
    return {lst["name"]: lst["id"] for lst in board["lists"]}


def add_card(client, user, list_id, title, **extra):
    response = client.post(f"/api/lists/{list_id}/cards", json={"title": title, **extra}, headers=auth_headers(user))
    assert response.status_code == 201, response.text
    return response.json()


def board_layout(client, user, board_id, include_archived=False):
    """{"To do": ["a", "b"], ...} — the board as the user sees it."""
    url = f"/api/boards/{board_id}" + ("?include_archived=true" if include_archived else "")
    board = client.get(url, headers=auth_headers(user)).json()
    return {lst["name"]: [c["title"] for c in lst["cards"]] for lst in board["lists"]}


def move(client, user, card, list_id, after=None):
    return client.post(
        f"/api/cards/{card['id']}/move",
        json={"list_id": list_id, "after_id": after["id"] if after else None},
        headers=auth_headers(user),
    )


# ── Create / read / update ──


def test_cards_are_added_at_the_bottom_and_shown_on_the_board(client, user):
    board = create_board(client, user)
    todo = lists_by_name(board)["To do"]
    card = add_card(client, user, todo, "Buy milk", description="Oat", due_at="2026-12-01T10:00:00+01:00")
    add_card(client, user, todo, "Call mum")

    assert card["board_id"] == board["id"]
    assert card["created_by_id"] == user.id
    assert datetime.fromisoformat(card["due_at"]) == datetime.fromisoformat("2026-12-01T09:00:00+00:00")
    assert board_layout(client, user, board["id"]) == {"To do": ["Buy milk", "Call mum"], "Doing": [], "Done": []}


def test_due_dates_need_a_timezone(client, user):
    todo = lists_by_name(create_board(client, user))["To do"]
    response = client.post(
        f"/api/lists/{todo}/cards", json={"title": "x", "due_at": "2026-12-01T10:00:00"}, headers=auth_headers(user)
    )
    assert response.status_code == 422


def test_update_card_fields(client, user):
    todo = lists_by_name(create_board(client, user))["To do"]
    card = add_card(client, user, todo, "Draft", description="Old", due_at="2026-12-01T10:00:00Z")
    url = f"/api/cards/{card['id']}"

    response = client.patch(url, json={"title": "Final", "description": None, "due_at": None}, headers=auth_headers(user))
    body = response.json()
    assert (body["title"], body["description"], body["due_at"]) == ("Final", None, None)

    # Unsent fields stay as they are.
    assert client.patch(url, json={"completed": True}, headers=auth_headers(user)).json()["title"] == "Final"


def test_completing_twice_keeps_the_first_timestamp(client, user):
    todo = lists_by_name(create_board(client, user))["To do"]
    card = add_card(client, user, todo, "Task")
    url = f"/api/cards/{card['id']}"

    first = client.patch(url, json={"completed": True}, headers=auth_headers(user)).json()["completed_at"]
    second = client.patch(url, json={"completed": True}, headers=auth_headers(user)).json()["completed_at"]
    assert first is not None and first == second
    assert client.patch(url, json={"completed": False}, headers=auth_headers(user)).json()["completed_at"] is None


def test_archived_cards_are_hidden_unless_asked_for(client, user):
    board = create_board(client, user)
    todo = lists_by_name(board)["To do"]
    card = add_card(client, user, todo, "Old")
    add_card(client, user, todo, "New")

    client.patch(f"/api/cards/{card['id']}", json={"archived": True}, headers=auth_headers(user))
    assert board_layout(client, user, board["id"])["To do"] == ["New"]
    assert board_layout(client, user, board["id"], include_archived=True)["To do"] == ["Old", "New"]


def test_delete_card(client, user):
    todo = lists_by_name(create_board(client, user))["To do"]
    card = add_card(client, user, todo, "Gone")
    assert client.delete(f"/api/cards/{card['id']}", headers=auth_headers(user)).status_code == 204
    assert client.get(f"/api/cards/{card['id']}", headers=auth_headers(user)).status_code == 404


def test_cannot_add_cards_to_archived_list(client, user):
    todo = lists_by_name(create_board(client, user))["To do"]
    client.patch(f"/api/lists/{todo}", json={"archived": True}, headers=auth_headers(user))
    response = client.post(f"/api/lists/{todo}/cards", json={"title": "x"}, headers=auth_headers(user))
    assert response.status_code == 422


# ── Moving ──


def test_reorder_within_a_list(client, user):
    board = create_board(client, user)
    todo = lists_by_name(board)["To do"]
    a, b, c = (add_card(client, user, todo, t) for t in "abc")

    assert move(client, user, c, todo, after=a).status_code == 200
    assert board_layout(client, user, board["id"])["To do"] == ["a", "c", "b"]
    move(client, user, b, todo, after=None)
    assert board_layout(client, user, board["id"])["To do"] == ["b", "a", "c"]


def test_move_to_another_list(client, user):
    board = create_board(client, user)
    ids = lists_by_name(board)
    a = add_card(client, user, ids["To do"], "a")
    x = add_card(client, user, ids["Doing"], "x")
    y = add_card(client, user, ids["Doing"], "y")

    moved = move(client, user, a, ids["Doing"], after=x).json()
    assert moved["list_id"] == ids["Doing"]
    assert board_layout(client, user, board["id"]) == {"To do": [], "Doing": ["x", "a", "y"], "Done": []}

    # Into an empty list.
    move(client, user, y, ids["Done"])
    assert board_layout(client, user, board["id"])["Done"] == ["y"]


def test_many_moves_into_the_same_gap_still_order_correctly(client, user):
    board = create_board(client, user)
    todo = lists_by_name(board)["To do"]
    a, b, c = (add_card(client, user, todo, t) for t in "abc")
    for i in range(80):
        assert move(client, user, b if i % 2 == 0 else c, todo, after=a).status_code == 200
    assert board_layout(client, user, board["id"])["To do"] == ["a", "c", "b"]


def test_invalid_moves(client, user):
    board = create_board(client, user)
    ids = lists_by_name(board)
    other_board = create_board(client, user, name="Other")
    a = add_card(client, user, ids["To do"], "a")
    in_doing = add_card(client, user, ids["Doing"], "in doing")

    # A list on another board, even one you own.
    assert move(client, user, a, other_board["lists"][0]["id"]).status_code == 422
    # after_id must be in the *target* list.
    assert move(client, user, a, ids["Done"], after=in_doing).status_code == 422
    assert move(client, user, a, ids["To do"], after=a).status_code == 422
    # Into an archived list.
    client.patch(f"/api/lists/{ids['Done']}", json={"archived": True}, headers=auth_headers(user))
    assert move(client, user, a, ids["Done"]).status_code == 422


# ── Permissions ──


def test_card_permissions(client, make_user, user):
    viewer = make_user(email="viewer@example.com")
    outsider = make_user(email="outsider@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], viewer.email, role="viewer")
    todo = lists_by_name(board)["To do"]
    card = add_card(client, user, todo, "Secret")
    url = f"/api/cards/{card['id']}"

    assert client.get(url, headers=auth_headers(viewer)).status_code == 200
    assert client.patch(url, json={"title": "x"}, headers=auth_headers(viewer)).status_code == 403
    assert move(client, viewer, card, todo).status_code == 403
    assert client.post(f"/api/lists/{todo}/cards", json={"title": "x"}, headers=auth_headers(viewer)).status_code == 403

    response = client.get(url, headers=auth_headers(outsider))
    assert (response.status_code, response.json()["detail"]) == (404, "Card not found")


# ── Performance ──


def _fill(client, make_user, owner, board_id, lists, cards_per_list, members, tag):
    """Add lists of cards, each card with a label, an assignee, a checklist item and a comment."""
    h = auth_headers(owner)
    users = [make_user(email=f"{tag}{i}@example.com") for i in range(members)]
    for u in users:
        add_member(client, owner, board_id, u.email)
    labels = [
        client.post(f"/api/boards/{board_id}/labels", json={"name": f"{tag}{i}", "color": "red"}, headers=h).json()
        for i in range(members)
    ]
    for i in range(lists):
        lst = client.post(f"/api/boards/{board_id}/lists", json={"name": f"{tag}{i}"}, headers=h).json()
        for j in range(cards_per_list):
            card = add_card(client, owner, lst["id"], f"{tag} {i}-{j}")
            k = (i + j) % members
            client.put(f"/api/cards/{card['id']}/labels/{labels[k]['id']}", headers=h)
            client.put(f"/api/cards/{card['id']}/assignees/{users[k].id}", headers=h)
            client.post(f"/api/cards/{card['id']}/checklist", json={"text": "step"}, headers=h)
            client.post(f"/api/cards/{card['id']}/comments", json={"body": "note"}, headers=h)


def _queries_to_load_board(client, db_session, count_queries, user, board_id):
    # Tests share one session across requests; in production each request gets a fresh one.
    # Empty the identity map so nothing is served from a previous request's cache.
    db_session.expunge_all()
    count_queries.clear()
    assert client.get(f"/api/boards/{board_id}", headers=auth_headers(user)).status_code == 200
    return len(count_queries)


def test_board_detail_query_count_does_not_grow_with_board_size(client, db_session, make_user, user, count_queries):
    """The N+1 guard: loading a board takes the same number of queries with one of everything
    as with many (4 vs 54 lists... 1 vs 50 cards, each with labels, assignees, checklists, comments).

    It starts from "one of everything", not an empty board, because SQLAlchemy skips a selectinload
    query when there are no parent rows: an empty board legitimately needs fewer queries.
    """
    board = create_board(client, user)
    _fill(client, make_user, user, board["id"], lists=1, cards_per_list=1, members=1, tag="a")
    small = _queries_to_load_board(client, db_session, count_queries, user, board["id"])

    _fill(client, make_user, user, board["id"], lists=10, cards_per_list=5, members=5, tag="b")
    large = _queries_to_load_board(client, db_session, count_queries, user, board["id"])

    assert large == small, f"{small} queries with one of everything, {large} with many"
