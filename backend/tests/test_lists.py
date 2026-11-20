from tests.conftest import auth_headers
from tests.test_boards import add_member, create_board


def list_names(client, user, board_id, include_archived=False):
    url = f"/api/boards/{board_id}" + ("?include_archived=true" if include_archived else "")
    return [lst["name"] for lst in client.get(url, headers=auth_headers(user)).json()["lists"]]


def list_ids(client, user, board_id):
    return {lst["name"]: lst["id"] for lst in client.get(f"/api/boards/{board_id}", headers=auth_headers(user)).json()["lists"]}


def test_new_list_goes_at_the_end(client, user):
    board = create_board(client, user)
    response = client.post(f"/api/boards/{board['id']}/lists", json={"name": "Later"}, headers=auth_headers(user))
    assert response.status_code == 201
    assert list_names(client, user, board["id"]) == ["To do", "Doing", "Done", "Later"]


def test_rename_list(client, user):
    board = create_board(client, user)
    ids = list_ids(client, user, board["id"])
    response = client.patch(f"/api/lists/{ids['Doing']}", json={"name": "In progress"}, headers=auth_headers(user))
    assert response.json()["name"] == "In progress"


def test_move_list(client, user):
    board = create_board(client, user)
    ids = list_ids(client, user, board["id"])

    client.post(f"/api/lists/{ids['Done']}/move", json={"after_id": ids["To do"]}, headers=auth_headers(user))
    assert list_names(client, user, board["id"]) == ["To do", "Done", "Doing"]

    client.post(f"/api/lists/{ids['Doing']}/move", json={"after_id": None}, headers=auth_headers(user))
    assert list_names(client, user, board["id"]) == ["Doing", "To do", "Done"]


def test_many_moves_into_the_same_gap_still_order_correctly(client, user):
    """Enough moves to exhaust float precision, forcing a renumber of the board's lists."""
    board = create_board(client, user)
    ids = list_ids(client, user, board["id"])
    # Alternate Doing and Done into the slot right after "To do": each move halves the gap.
    for i in range(80):
        moving = ids["Doing"] if i % 2 == 0 else ids["Done"]
        response = client.post(f"/api/lists/{moving}/move", json={"after_id": ids["To do"]}, headers=auth_headers(user))
        assert response.status_code == 200
    assert list_names(client, user, board["id"]) == ["To do", "Done", "Doing"]


def test_move_rejects_bad_after_id(client, user):
    board = create_board(client, user)
    other_board = create_board(client, user, name="Other")
    ids = list_ids(client, user, board["id"])
    other_list = other_board["lists"][0]["id"]

    for after_id in (ids["Doing"], other_list, 99999):
        response = client.post(f"/api/lists/{ids['Doing']}/move", json={"after_id": after_id}, headers=auth_headers(user))
        assert response.status_code == 422

    # after_id is required: forgetting it must not silently move the list to the start.
    assert client.post(f"/api/lists/{ids['Doing']}/move", json={}, headers=auth_headers(user)).status_code == 422


def test_archive_and_restore_list(client, user):
    board = create_board(client, user)
    ids = list_ids(client, user, board["id"])

    client.patch(f"/api/lists/{ids['Doing']}", json={"archived": True}, headers=auth_headers(user))
    assert list_names(client, user, board["id"]) == ["To do", "Done"]
    assert list_names(client, user, board["id"], include_archived=True) == ["To do", "Doing", "Done"]

    client.patch(f"/api/lists/{ids['Doing']}", json={"archived": False}, headers=auth_headers(user))
    assert list_names(client, user, board["id"]) == ["To do", "Doing", "Done"]  # Back in its old slot.


def test_list_permissions(client, make_user, user):
    viewer = make_user(email="viewer@example.com")
    outsider = make_user(email="outsider@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], viewer.email, role="viewer")
    list_id = board["lists"][0]["id"]

    assert client.post(f"/api/boards/{board['id']}/lists", json={"name": "x"}, headers=auth_headers(viewer)).status_code == 403
    assert client.patch(f"/api/lists/{list_id}", json={"name": "x"}, headers=auth_headers(viewer)).status_code == 403
    # Outsiders can't tell the list exists.
    response = client.patch(f"/api/lists/{list_id}", json={"name": "x"}, headers=auth_headers(outsider))
    assert response.status_code == 404
    assert response.json()["detail"] == "List not found"
