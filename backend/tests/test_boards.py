from ptashka.models.db import UserRole
from tests.conftest import auth_headers


def create_board(client, user, name="Home", **extra):
    response = client.post("/api/boards", json={"name": name, **extra}, headers=auth_headers(user))
    assert response.status_code == 201, response.text
    return response.json()


def add_member(client, owner, board_id, email, role="editor"):
    return client.post(
        f"/api/boards/{board_id}/members", json={"email": email, "role": role}, headers=auth_headers(owner)
    )


# ── Boards ──


def test_create_board_makes_you_owner_with_default_lists(client, user):
    board = create_board(client, user, description="Chores")
    assert board["my_role"] == "owner"
    assert board["description"] == "Chores"
    assert [lst["name"] for lst in board["lists"]] == ["To do", "Doing", "Done"]
    assert [m["user"]["id"] for m in board["members"]] == [user.id]


def test_create_board_without_default_lists(client, user):
    assert create_board(client, user, default_lists=False)["lists"] == []


def test_board_list_only_shows_your_boards(client, make_user, user):
    other = make_user(email="other@example.com")
    create_board(client, user, name="Mine")
    create_board(client, other, name="Theirs")

    boards = client.get("/api/boards", headers=auth_headers(user)).json()["boards"]
    assert [b["name"] for b in boards] == ["Mine"]


def test_non_members_get_404_not_403(client, make_user, user):
    """Outsiders can't tell a private board from a missing one."""
    outsider = make_user(email="outsider@example.com")
    board = create_board(client, user)

    assert client.get(f"/api/boards/{board['id']}", headers=auth_headers(outsider)).status_code == 404
    assert client.get("/api/boards/99999", headers=auth_headers(outsider)).status_code == 404


def test_site_admins_have_no_special_board_access(client, user, admin):
    board = create_board(client, user)
    assert client.get(f"/api/boards/{board['id']}", headers=auth_headers(admin)).status_code == 404


def test_viewer_can_read_but_not_edit(client, make_user, user):
    viewer = make_user(email="viewer@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], viewer.email, role="viewer")

    assert client.get(f"/api/boards/{board['id']}", headers=auth_headers(viewer)).json()["my_role"] == "viewer"
    response = client.patch(f"/api/boards/{board['id']}", json={"name": "Hacked"}, headers=auth_headers(viewer))
    assert response.status_code == 403


def test_editor_can_rename_but_only_owner_can_archive(client, make_user, user):
    editor = make_user(email="editor@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], editor.email)
    url = f"/api/boards/{board['id']}"

    response = client.patch(url, json={"name": "Renamed", "description": None}, headers=auth_headers(editor))
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["description"] is None

    assert client.patch(url, json={"archived": True}, headers=auth_headers(editor)).status_code == 403
    assert client.patch(url, json={"archived": True}, headers=auth_headers(user)).json()["archived_at"] is not None


def test_patch_leaves_unsent_fields_alone(client, user):
    board = create_board(client, user, description="Keep me")
    response = client.patch(f"/api/boards/{board['id']}", json={"name": "New"}, headers=auth_headers(user))
    assert response.json()["description"] == "Keep me"


def test_archived_boards_are_hidden_unless_asked_for(client, user):
    board = create_board(client, user)
    client.patch(f"/api/boards/{board['id']}", json={"archived": True}, headers=auth_headers(user))

    assert client.get("/api/boards", headers=auth_headers(user)).json()["boards"] == []
    archived = client.get("/api/boards?include_archived=true", headers=auth_headers(user)).json()["boards"]
    assert [b["id"] for b in archived] == [board["id"]]

    client.patch(f"/api/boards/{board['id']}", json={"archived": False}, headers=auth_headers(user))
    assert len(client.get("/api/boards", headers=auth_headers(user)).json()["boards"]) == 1


def test_only_owner_can_delete_board(client, make_user, user):
    editor = make_user(email="editor@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], editor.email)
    url = f"/api/boards/{board['id']}"

    assert client.delete(url, headers=auth_headers(editor)).status_code == 403
    assert client.delete(url, headers=auth_headers(user)).status_code == 204
    assert client.get(url, headers=auth_headers(user)).status_code == 404


# ── Members ──


def test_add_member_by_email(client, make_user, user):
    friend = make_user(email="friend@example.com")
    board = create_board(client, user)

    response = add_member(client, user, board["id"], "  Friend@Example.com ")
    assert response.status_code == 201
    assert response.json()["user"]["id"] == friend.id
    assert response.json()["role"] == "editor"

    assert add_member(client, user, board["id"], friend.email).status_code == 409
    boards = client.get("/api/boards", headers=auth_headers(friend)).json()["boards"]
    assert [b["my_role"] for b in boards] == ["editor"]


def test_cannot_add_unknown_or_pending_users(client, make_user, user):
    from ptashka.models.db import UserStatus

    make_user(email="pending@example.com", status=UserStatus.PENDING)
    board = create_board(client, user)
    assert add_member(client, user, board["id"], "nobody@example.com").status_code == 404
    assert add_member(client, user, board["id"], "pending@example.com").status_code == 404


def test_only_owners_manage_members(client, make_user, user):
    editor = make_user(email="editor@example.com")
    make_user(email="third@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], editor.email)

    assert add_member(client, editor, board["id"], "third@example.com").status_code == 403
    response = client.patch(
        f"/api/boards/{board['id']}/members/{editor.id}", json={"role": "owner"}, headers=auth_headers(editor)
    )
    assert response.status_code == 403


def test_last_owner_cannot_leave_or_be_demoted(client, make_user, user):
    board = create_board(client, user)
    member_url = f"/api/boards/{board['id']}/members/{user.id}"

    assert client.patch(member_url, json={"role": "editor"}, headers=auth_headers(user)).status_code == 409
    assert client.delete(member_url, headers=auth_headers(user)).status_code == 409

    # With a second owner, the first one can step down.
    co_owner = make_user(email="co@example.com")
    add_member(client, user, board["id"], co_owner.email, role="owner")
    assert client.patch(member_url, json={"role": "editor"}, headers=auth_headers(user)).status_code == 200


def test_member_can_leave_but_not_remove_others(client, make_user, user):
    a = make_user(email="a@example.com")
    b = make_user(email="b@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], a.email)
    add_member(client, user, board["id"], b.email)
    members_url = f"/api/boards/{board['id']}/members"

    assert client.delete(f"{members_url}/{b.id}", headers=auth_headers(a)).status_code == 403
    assert client.delete(f"{members_url}/{a.id}", headers=auth_headers(a)).status_code == 204
    assert client.get(f"/api/boards/{board['id']}", headers=auth_headers(a)).status_code == 404


def test_deleting_a_user_removes_their_memberships(client, db_session, make_user, user):
    friend = make_user(email="friend@example.com", role=UserRole.USER)
    board = create_board(client, user)
    add_member(client, user, board["id"], friend.email)

    db_session.delete(friend)
    db_session.commit()
    members = client.get(f"/api/boards/{board['id']}/members", headers=auth_headers(user)).json()["members"]
    assert [m["user"]["id"] for m in members] == [user.id]
