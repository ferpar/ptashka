"""The contributor role: works on cards without managing them. One test per row of the permission table."""

from dataclasses import dataclass
from typing import Any

import pytest

from ptashka.models.db import BoardRole, User
from tests.conftest import auth_headers
from tests.test_boards import add_member, create_board
from tests.test_cards import add_card, lists_by_name


def test_roles_form_a_ladder():
    assert list(BoardRole) == [BoardRole.VIEWER, BoardRole.CONTRIBUTOR, BoardRole.EDITOR, BoardRole.OWNER]
    assert BoardRole.CONTRIBUTOR.includes(BoardRole.VIEWER)
    assert not BoardRole.CONTRIBUTOR.includes(BoardRole.EDITOR)


@dataclass
class Setup:
    owner: User
    contributor: User
    viewer: User
    board: dict[str, Any]
    lists: dict[str, int]
    card: dict[str, Any]
    item: dict[str, Any]
    label: dict[str, Any]


@pytest.fixture
def s(client, make_user, user) -> Setup:
    contributor = make_user(email="contributor@example.com")
    viewer = make_user(email="viewer@example.com")
    board = create_board(client, user)
    add_member(client, user, board["id"], contributor.email, role="contributor")
    add_member(client, user, board["id"], viewer.email, role="viewer")
    lists = lists_by_name(board)
    card = add_card(client, user, lists["To do"], "Task", description="Spec")
    item = client.post(f"/api/cards/{card['id']}/checklist", json={"text": "step"}, headers=auth_headers(user)).json()
    label = client.post(f"/api/boards/{board['id']}/labels", json={"name": "bug", "color": "red"}, headers=auth_headers(user)).json()
    return Setup(user, contributor, viewer, board, lists, card, item, label)


def as_(client, who: User):
    """Tiny helper: requests as a given user."""
    h = auth_headers(who)

    class Requests:
        def get(self, url):
            return client.get(url, headers=h)

        def post(self, url, body=None):
            return client.post(url, json=body or {}, headers=h)

        def patch(self, url, body):
            return client.patch(url, json=body, headers=h)

        def put(self, url):
            return client.put(url, headers=h)

        def delete(self, url):
            return client.delete(url, headers=h)

    return Requests()


# ── What contributors can do ──


def test_contributor_reads_everything(client, s):
    c = as_(client, s.contributor)
    assert c.get(f"/api/boards/{s.board['id']}").json()["my_role"] == "contributor"
    assert c.get(f"/api/cards/{s.card['id']}").status_code == 200


def test_contributor_moves_cards_and_done_completes_them(client, s):
    c = as_(client, s.contributor)
    response = c.post(f"/api/cards/{s.card['id']}/move", {"list_id": s.lists["Done"], "after_id": None})
    assert response.status_code == 200
    assert response.json()["completed_at"] is not None


def test_contributor_completes_and_reopens(client, s):
    c = as_(client, s.contributor)
    url = f"/api/cards/{s.card['id']}"
    assert c.patch(url, {"completed": True, "version": s.card["version"]}).json()["completed_at"] is not None
    assert c.patch(url, {"completed": False}).json()["completed_at"] is None


def test_contributor_ticks_checklist_items(client, s):
    c = as_(client, s.contributor)
    assert c.patch(f"/api/checklist-items/{s.item['id']}", {"done": True}).json()["done_at"] is not None


def test_contributor_comments_and_manages_own_comments(client, s):
    c = as_(client, s.contributor)
    note = c.post(f"/api/cards/{s.card['id']}/comments", {"body": "On it"}).json()
    assert c.patch(f"/api/comments/{note['id']}", {"body": "Done, see PR"}).status_code == 200
    assert c.delete(f"/api/comments/{note['id']}").status_code == 204


def test_contributor_assigns_and_unassigns_themselves(client, s):
    c = as_(client, s.contributor)
    url = f"/api/cards/{s.card['id']}/assignees/{s.contributor.id}"
    assert c.put(url).status_code == 204
    assert c.get(f"/api/cards/{s.card['id']}").json()["assignee_ids"] == [s.contributor.id]
    assert c.delete(url).status_code == 204


# ── What contributors can't do ──


def test_contributor_cannot_assign_others(client, s):
    c = as_(client, s.contributor)
    response = c.put(f"/api/cards/{s.card['id']}/assignees/{s.owner.id}")
    assert response.status_code == 403
    # ...nor take someone else off a card.
    as_(client, s.owner).put(f"/api/cards/{s.card['id']}/assignees/{s.owner.id}")
    assert c.delete(f"/api/cards/{s.card['id']}/assignees/{s.owner.id}").status_code == 403


@pytest.mark.parametrize(
    "field_change",
    [{"title": "Rewritten"}, {"description": None}, {"due_at": "2026-12-01T10:00:00Z"}, {"archived": True}],
)
def test_contributor_cannot_edit_card_fields(client, s, field_change):
    response = as_(client, s.contributor).patch(f"/api/cards/{s.card['id']}", field_change)
    assert response.status_code == 403
    assert "editor" in response.json()["detail"]


def test_mixing_allowed_and_forbidden_fields_changes_nothing(client, s):
    """All or nothing: `completed` alone would be fine, but not alongside `title`."""
    c = as_(client, s.contributor)
    assert c.patch(f"/api/cards/{s.card['id']}", {"completed": True, "title": "Sneaky"}).status_code == 403
    card = c.get(f"/api/cards/{s.card['id']}").json()
    assert (card["title"], card["completed_at"]) == ("Task", None)


def test_contributor_cannot_create_or_delete_cards(client, s):
    c = as_(client, s.contributor)
    assert c.post(f"/api/lists/{s.lists['To do']}/cards", {"title": "New"}).status_code == 403
    assert c.delete(f"/api/cards/{s.card['id']}").status_code == 403


def test_contributor_cannot_restructure_checklists(client, s):
    c = as_(client, s.contributor)
    assert c.patch(f"/api/checklist-items/{s.item['id']}", {"text": "Changed"}).status_code == 403
    assert c.post(f"/api/cards/{s.card['id']}/checklist", {"text": "More"}).status_code == 403
    assert c.post(f"/api/checklist-items/{s.item['id']}/move", {"after_id": None}).status_code == 403
    assert c.delete(f"/api/checklist-items/{s.item['id']}").status_code == 403


def test_contributor_cannot_manage_labels_or_lists(client, s):
    c = as_(client, s.contributor)
    assert c.post(f"/api/boards/{s.board['id']}/labels", {"name": "x", "color": "red"}).status_code == 403
    assert c.put(f"/api/cards/{s.card['id']}/labels/{s.label['id']}").status_code == 403
    assert c.post(f"/api/boards/{s.board['id']}/lists", {"name": "x"}).status_code == 403
    assert c.patch(f"/api/lists/{s.lists['To do']}", {"name": "x"}).status_code == 403


def test_contributor_cannot_manage_the_board(client, s):
    c = as_(client, s.contributor)
    assert c.patch(f"/api/boards/{s.board['id']}", {"name": "x"}).status_code == 403
    assert c.post(f"/api/boards/{s.board['id']}/members", {"email": "x@example.com"}).status_code == 403


# ── Viewers stay strictly read-only ──


def test_viewer_cannot_do_contributor_things(client, s):
    v = as_(client, s.viewer)
    assert v.get(f"/api/cards/{s.card['id']}").status_code == 200
    assert v.post(f"/api/cards/{s.card['id']}/move", {"list_id": s.lists["Done"], "after_id": None}).status_code == 403
    assert v.patch(f"/api/cards/{s.card['id']}", {"completed": True}).status_code == 403
    assert v.patch(f"/api/checklist-items/{s.item['id']}", {"done": True}).status_code == 403
    assert v.post(f"/api/cards/{s.card['id']}/comments", {"body": "hi"}).status_code == 403
    assert v.put(f"/api/cards/{s.card['id']}/assignees/{s.viewer.id}").status_code == 403


def test_owner_can_promote_a_viewer_to_contributor(client, s):
    response = as_(client, s.owner).patch(
        f"/api/boards/{s.board['id']}/members/{s.viewer.id}", {"role": "contributor"}
    )
    assert response.json()["role"] == "contributor"
    assert as_(client, s.viewer).post(f"/api/cards/{s.card['id']}/comments", {"body": "now I can"}).status_code == 201
