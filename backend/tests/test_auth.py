from ptashka.services import auth_service
from tests.conftest import auth_headers

REGISTRATION = {"email": "Olena@Example.com", "password": "password123", "display_name": "Olena"}
LOGIN = {"email": "olena@example.com", "password": "password123"}


def test_registration_creates_pending_account_without_tokens(client):
    response = client.post("/api/auth/register", json=REGISTRATION)
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["status"] == "pending"
    assert body["user"]["email"] == "olena@example.com"
    assert "tokens" not in body
    assert "hashed_password" not in body["user"]


def test_registration_validates_input(client):
    response = client.post("/api/auth/register", json={**REGISTRATION, "email": "not-an-email", "password": "short"})
    assert response.status_code == 422
    bad_fields = {error["loc"][-1] for error in response.json()["detail"]}
    assert bad_fields == {"email", "password"}


def test_duplicate_email_is_rejected(client):
    client.post("/api/auth/register", json=REGISTRATION)
    assert client.post("/api/auth/register", json=REGISTRATION).status_code == 409


def test_pending_account_cannot_log_in(client):
    client.post("/api/auth/register", json=REGISTRATION)
    response = client.post("/api/auth/login", json=LOGIN)
    assert response.status_code == 403
    assert response.json()["detail"] == "account_pending"


def test_wrong_password_is_401_even_for_pending_accounts(client):
    client.post("/api/auth/register", json=REGISTRATION)
    response = client.post("/api/auth/login", json={**LOGIN, "password": "nope-nope"})
    assert response.status_code == 401


def test_admin_approval_enables_login_and_refresh(client, admin):
    user_id = client.post("/api/auth/register", json=REGISTRATION).json()["user"]["id"]

    pending = client.get("/api/admin/users?status=pending", headers=auth_headers(admin)).json()["users"]
    assert [u["id"] for u in pending] == [user_id]

    response = client.patch(f"/api/admin/users/{user_id}", json={"status": "active"}, headers=auth_headers(admin))
    assert response.json()["status"] == "active"

    login = client.post("/api/auth/login", json=LOGIN)
    assert login.status_code == 200
    tokens = login.json()["tokens"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.json()["display_name"] == "Olena"

    refreshed = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200


def test_logout_revokes_refresh_token(client, user):
    tokens = client.post("/api/auth/login", json={"email": user.email, "password": "password123"}).json()["tokens"]
    client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_disabling_revokes_refresh_tokens_and_access(client, admin, user):
    tokens = client.post("/api/auth/login", json={"email": user.email, "password": "password123"}).json()["tokens"]

    client.patch(f"/api/admin/users/{user.id}", json={"status": "disabled"}, headers=auth_headers(admin))

    assert client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.get("/api/auth/me", headers=auth_headers(user)).status_code == 401


def test_requests_without_token_are_rejected(client):
    assert client.get("/api/auth/me").status_code in (401, 403)
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_admin_endpoints_require_admin(client, user):
    assert client.get("/api/admin/users", headers=auth_headers(user)).status_code == 403


def test_admin_cannot_demote_themselves(client, admin):
    response = client.patch(f"/api/admin/users/{admin.id}", json={"role": "user"}, headers=auth_headers(admin))
    assert response.status_code == 400


def test_profile_update(client, user):
    response = client.patch("/api/auth/me", json={"display_name": "New Name"}, headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["display_name"] == "New Name"


def test_unknown_emails_still_run_bcrypt(client, user, monkeypatch):
    """Timing-attack guard: unknown and known emails must cost the same bcrypt check.
    (Asserted by counting calls, not by measuring time, which would be flaky.)"""
    calls = []
    real_verify = auth_service.verify_password
    monkeypatch.setattr(auth_service, "verify_password", lambda pw, h: calls.append(h) or real_verify(pw, h))

    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever1"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": user.email, "password": "wrong-pass"}).status_code == 401
    assert len(calls) == 2


def test_registration_hashes_before_touching_the_database(client, count_queries, monkeypatch):
    """No connection should sit idle in a transaction while bcrypt runs (~170 ms)."""
    queries_before_hash = []
    real_hash = auth_service.hash_password
    monkeypatch.setattr(auth_service, "hash_password", lambda pw: queries_before_hash.append(len(count_queries)) or real_hash(pw))

    count_queries.clear()
    assert client.post("/api/auth/register", json=REGISTRATION).status_code == 201
    assert queries_before_hash == [0]
