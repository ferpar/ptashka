"""Cross-board search: GET /api/cards."""

from datetime import datetime, timedelta, timezone

from tests.conftest import auth_headers
from tests.test_boards import add_member, create_board
from tests.test_cards import add_card, lists_by_name, move


def search(client, user, **params):
    response = client.get("/api/cards", params=params, headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return response.json()


def titles(client, user, **params):
    return [c["title"] for c in search(client, user, **params)["cards"]]


def iso(dt):
    return dt.isoformat()


NOW = datetime.now(timezone.utc)


def test_only_boards_you_belong_to(client, make_user, user):
    stranger = make_user(email="stranger@example.com")
    add_card(client, user, lists_by_name(create_board(client, user))["To do"], "Mine")
    add_card(client, stranger, lists_by_name(create_board(client, stranger))["To do"], "Theirs")
    assert titles(client, user) == ["Mine"]


def test_results_say_where_cards_live_and_carry_counts(client, user):
    board = create_board(client, user, name="Work")
    card = add_card(client, user, lists_by_name(board)["Doing"], "Task")
    client.post(f"/api/cards/{card['id']}/checklist", json={"text": "step"}, headers=auth_headers(user))
    hit = search(client, user)["cards"][0]
    assert (hit["board_name"], hit["list_name"], hit["checklist_total"], hit["comment_count"]) == ("Work", "Doing", 1, 0)


def test_my_open_tasks_across_boards(client, make_user, user):
    friend = make_user(email="friend@example.com")
    work, home = create_board(client, user, name="Work"), create_board(client, user, name="Home")
    add_member(client, user, work["id"], friend.email)
    mine_work = add_card(client, user, lists_by_name(work)["To do"], "Mine at work")
    mine_home = add_card(client, user, lists_by_name(home)["To do"], "Mine at home")
    theirs = add_card(client, user, lists_by_name(work)["To do"], "Friend's")
    done = add_card(client, user, lists_by_name(home)["To do"], "Mine, done")
    for c in (mine_work, mine_home, done):
        client.put(f"/api/cards/{c['id']}/assignees/{user.id}", headers=auth_headers(user))
    client.put(f"/api/cards/{theirs['id']}/assignees/{friend.id}", headers=auth_headers(user))
    move(client, user, done, lists_by_name(home)["Done"])

    assert sorted(titles(client, user, assignee="me", completed=False)) == ["Mine at home", "Mine at work"]
    assert titles(client, user, assignee=str(friend.id)) == ["Friend's"]
    assert titles(client, user, assignee="me", board_id=home["id"]) == ["Mine at home", "Mine, done"]
    assert client.get("/api/cards", params={"assignee": "nobody"}, headers=auth_headers(user)).status_code == 422


def test_label_filter_matches_by_name_across_boards(client, user):
    boards = [create_board(client, user, name=n) for n in ("A", "B")]
    for b in boards:
        label = client.post(f"/api/boards/{b['id']}/labels", json={"name": "Urgent", "color": "red"}, headers=auth_headers(user)).json()
        card = add_card(client, user, lists_by_name(b)["To do"], f"urgent on {b['name']}")
        client.put(f"/api/cards/{card['id']}/labels/{label['id']}", headers=auth_headers(user))
        add_card(client, user, lists_by_name(b)["To do"], f"calm on {b['name']}")

    assert sorted(titles(client, user, label="urgent")) == ["urgent on A", "urgent on B"]


def test_due_dates_overdue_and_sorting(client, user):
    todo = lists_by_name(board := create_board(client, user))["To do"]
    add_card(client, user, todo, "no date")
    add_card(client, user, todo, "next week", due_at=iso(NOW + timedelta(days=7)))
    add_card(client, user, todo, "tomorrow", due_at=iso(NOW + timedelta(days=1)))
    late = add_card(client, user, todo, "late", due_at=iso(NOW - timedelta(days=1)))
    finished = add_card(client, user, todo, "late but done", due_at=iso(NOW - timedelta(days=2)))
    move(client, user, finished, lists_by_name(board)["Done"])

    # Soonest first, undated last.
    assert titles(client, user) == ["late but done", "late", "tomorrow", "next week", "no date"]
    assert titles(client, user, overdue=True) == ["late"]
    assert titles(client, user, due_after=iso(NOW), due_before=iso(NOW + timedelta(days=3))) == ["tomorrow"]
    assert late  # (Its completed sibling shows `overdue` ignores finished work.)


def test_text_search_is_case_insensitive_and_takes_wildcards_literally(client, user):
    todo = lists_by_name(create_board(client, user))["To do"]
    add_card(client, user, todo, "Raise prices 100%")
    add_card(client, user, todo, "Raise prices 1000 times")
    add_card(client, user, todo, "Refactor", description="Rename snake_case helpers")
    add_card(client, user, todo, "Unrelated", description="snakeXcase")

    assert sorted(titles(client, user, q="RAISE")) == ["Raise prices 100%", "Raise prices 1000 times"]
    assert titles(client, user, q="100%") == ["Raise prices 100%"]  # % is not "anything".
    assert titles(client, user, q="snake_case") == ["Refactor"]  # _ is not "any character".


def test_archived_things_are_hidden_unless_asked_for(client, user):
    board = create_board(client, user)
    ids = lists_by_name(board)
    archived_card = add_card(client, user, ids["To do"], "archived card")
    add_card(client, user, ids["Doing"], "on archived list")
    add_card(client, user, ids["To do"], "visible")
    client.patch(f"/api/cards/{archived_card['id']}", json={"archived": True}, headers=auth_headers(user))
    client.patch(f"/api/lists/{ids['Doing']}", json={"archived": True}, headers=auth_headers(user))
    other = create_board(client, user, name="Old")
    add_card(client, user, lists_by_name(other)["To do"], "on archived board")
    client.patch(f"/api/boards/{other['id']}", json={"archived": True}, headers=auth_headers(user))

    assert titles(client, user) == ["visible"]
    assert len(titles(client, user, archived=True)) == 4


def test_pagination(client, user):
    todo = lists_by_name(create_board(client, user))["To do"]
    for i in range(5):
        add_card(client, user, todo, f"card {i}")
    first = search(client, user, limit=2)
    second = search(client, user, limit=2, offset=first["next_offset"])
    third = search(client, user, limit=2, offset=second["next_offset"])
    seen = [c["title"] for page in (first, second, third) for c in page["cards"]]
    assert seen == [f"card {i}" for i in range(5)] and third["next_offset"] is None


def test_read_tokens_can_search(client, user):
    add_card(client, user, lists_by_name(create_board(client, user))["To do"], "Findable")
    token = client.post("/api/tokens", json={"name": "agent", "scope": "read"}, headers=auth_headers(user)).json()["token"]
    response = client.get("/api/cards", params={"q": "find"}, headers={"Authorization": f"Bearer {token}"})
    assert [c["title"] for c in response.json()["cards"]] == ["Findable"]


def test_search_query_count_does_not_grow_with_results(client, db_session, user, count_queries):
    """Same N+1 guard as the board view: 1 hit or 20 hits, same number of queries."""
    board = create_board(client, user)
    todo = lists_by_name(board)["To do"]
    label = client.post(f"/api/boards/{board['id']}/labels", json={"name": "x", "color": "red"}, headers=auth_headers(user)).json()

    def add_full_card(i):
        card = add_card(client, user, todo, f"card {i}")
        client.put(f"/api/cards/{card['id']}/labels/{label['id']}", headers=auth_headers(user))
        client.put(f"/api/cards/{card['id']}/assignees/{user.id}", headers=auth_headers(user))

    def measure():
        headers = auth_headers(user)
        db_session.expunge_all()
        count_queries.clear()
        client.get("/api/cards", headers=headers)
        return len(count_queries)

    add_full_card(0)
    one = measure()
    for i in range(1, 20):
        add_full_card(i)
    assert measure() == one
