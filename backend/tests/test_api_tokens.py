"""Personal API tokens: how scripts and agents authenticate."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ptashka.models.db import ApiToken, UserRole, UserStatus
from tests.conftest import auth_headers
from tests.test_boards import add_member, create_board
from tests.test_cards import add_card, lists_by_name


def new_token(client, user, scope="read", **extra):
    response = client.post("/api/tokens", json={"name": "agent", "scope": scope, **extra}, headers=auth_headers(user))
    assert response.status_code == 201, response.text
    return response.json()


def bearer(token):
    return {"Authorization": f"Bearer {token['token']}"}


def test_create_shows_the_secret_once_and_stores_only_a_hash(client, db_session, user):
    created = new_token(client, user)
    assert created["token"].startswith("ptk_") and len(created["token"]) > 40
    assert created["prefix"] == created["token"][:12]
    assert created["scope"] == "read"

    listed = client.get("/api/tokens", headers=auth_headers(user)).json()["tokens"]
    assert [t["prefix"] for t in listed] == [created["prefix"]]
    assert "token" not in listed[0]
    stored = db_session.scalars(select(ApiToken)).one()
    assert created["token"] not in (stored.token_hash, stored.prefix)


def test_a_token_authenticates_as_its_user_and_records_use(client, user):
    token = new_token(client, user)
    assert token["last_used_at"] is None
    assert client.get("/api/auth/me", headers=bearer(token)).json()["id"] == user.id
    listed = client.get("/api/tokens", headers=auth_headers(user)).json()["tokens"]
    assert listed[0]["last_used_at"] is not None


def test_read_tokens_can_only_read(client, user):
    board = create_board(client, user)
    token = new_token(client, user, scope="read")

    assert client.get(f"/api/boards/{board['id']}", headers=bearer(token)).status_code == 200
    for response in (
        client.post("/api/boards", json={"name": "x"}, headers=bearer(token)),
        client.patch(f"/api/boards/{board['id']}", json={"name": "x"}, headers=bearer(token)),
        client.delete(f"/api/boards/{board['id']}", headers=bearer(token)),
    ):
        assert response.status_code == 403
        assert response.json()["detail"] == "This API token is read-only"


def test_write_tokens_are_still_limited_by_board_role(client, make_user, user):
    """The effective permission is the lower of token scope and board role."""
    agent = make_user(email="agent@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], agent.email, role="contributor")
    card = add_card(client, user, lists_by_name(board)["To do"], "Task")
    token = new_token(client, agent, scope="write")

    done = lists_by_name(board)["Done"]
    move = client.post(f"/api/cards/{card['id']}/move", json={"list_id": done, "after_id": None}, headers=bearer(token))
    assert move.status_code == 200  # Contributors may move...
    rename = client.patch(f"/api/cards/{card['id']}", json={"title": "x"}, headers=bearer(token))
    assert rename.status_code == 403  # ...but not edit, whatever the token allows.


def test_revoked_expired_and_unknown_tokens_are_rejected(client, db_session, user):
    revoked = new_token(client, user)
    assert client.delete(f"/api/tokens/{revoked['id']}", headers=auth_headers(user)).status_code == 204
    assert client.get("/api/auth/me", headers=bearer(revoked)).status_code == 401

    expiring = new_token(client, user, expires_in_days=1)
    assert client.get("/api/auth/me", headers=bearer(expiring)).status_code == 200
    row = db_session.get(ApiToken, expiring["id"])
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get("/api/auth/me", headers=bearer(expiring)).status_code == 401

    assert client.get("/api/auth/me", headers={"Authorization": "Bearer ptk_not-a-real-token"}).status_code == 401


def test_tokens_stop_working_when_the_user_is_disabled(client, db_session, user):
    token = new_token(client, user)
    user.status = UserStatus.DISABLED
    db_session.commit()
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_tokens_cannot_manage_tokens(client, user):
    """Otherwise a leaked read token could create itself a write token."""
    token = new_token(client, user, scope="write")
    assert client.post("/api/tokens", json={"name": "escalate", "scope": "write"}, headers=bearer(token)).status_code == 403
    assert client.get("/api/tokens", headers=bearer(token)).status_code == 403
    assert client.delete(f"/api/tokens/{token['id']}", headers=bearer(token)).status_code == 403


def test_tokens_cannot_use_admin_endpoints(client, make_user):
    admin = make_user(email="admin@example.com", role=UserRole.ADMIN)
    token = new_token(client, admin, scope="write")
    assert client.get("/api/admin/users", headers=bearer(token)).status_code == 403
    assert client.get("/api/admin/users", headers=auth_headers(admin)).status_code == 200


def test_you_cannot_revoke_someone_elses_token(client, make_user, user):
    other = make_user(email="other@example.com")
    theirs = new_token(client, other)
    assert client.delete(f"/api/tokens/{theirs['id']}", headers=auth_headers(user)).status_code == 404
    assert client.get("/api/auth/me", headers=bearer(theirs)).status_code == 200
