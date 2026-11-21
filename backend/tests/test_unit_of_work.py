"""The request is the unit of work: everything it changed commits together, or nothing does."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from ptashka.api import cards as cards_api
from ptashka.main import app
from ptashka.models.db import Label, LabelColor
from ptashka.services import board_service, card_service, label_service
from tests.conftest import auth_headers
from tests.test_boards import create_board
from tests.test_cards import add_card, lists_by_name


@pytest.fixture
def lenient_client(client):
    """Like `client` (same database override), but returns 500 responses instead of raising,
    so tests can check what a real client would receive."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def card(client, user):
    return add_card(client, user, lists_by_name(create_board(client, user))["To do"], "Original")


def title_of(client, user, card):
    return client.get(f"/api/cards/{card['id']}", headers=auth_headers(user)).json()["title"]


def test_failure_after_the_service_ran_saves_nothing(lenient_client, client, user, card, monkeypatch):
    """update_card has already changed and flushed the title when the response-building step blows up.
    The whole request must roll back: no half-done operations."""

    def explode(*_args, **_kwargs):
        raise RuntimeError("bug while building the response")

    monkeypatch.setattr(cards_api, "card_detail", explode)
    response = lenient_client.patch(f"/api/cards/{card['id']}", json={"title": "Changed"}, headers=auth_headers(user))
    assert response.status_code == 500
    monkeypatch.undo()

    assert title_of(client, user, card) == "Original"


def test_a_failed_commit_is_reported_not_hidden(lenient_client, client, db_session, user, card, monkeypatch):
    """With the default dependency scope the COMMIT would run after the response was sent, so the
    client would get a 200 for data that was never saved. scope="function" makes it a 500."""
    real_commit = db_session.commit

    def failing_commit():
        raise RuntimeError("connection lost during COMMIT")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    response = lenient_client.patch(f"/api/cards/{card['id']}", json={"title": "Changed"}, headers=auth_headers(user))
    assert response.status_code == 500
    monkeypatch.setattr(db_session, "commit", real_commit)

    assert title_of(client, user, card) == "Original"


def test_a_savepoint_rolls_back_only_the_failed_step(db_session, user):
    """Within one transaction: label A, a duplicate of A (fails), label B, then commit.
    The duplicate's failure must not take A or B down with it."""
    board = board_service.create_board(db_session, user, "B", None, default_lists=False)
    label_service.create_label(db_session, board, "a", LabelColor.RED)
    with pytest.raises(label_service.LabelExistsError):
        label_service.create_label(db_session, board, "a", LabelColor.BLUE)
    label_service.create_label(db_session, board, "b", LabelColor.GREEN)
    db_session.commit()

    names = db_session.scalars(select(Label.name).where(Label.board_id == board.id).order_by(Label.name)).all()
    assert names == ["a", "b"]


def test_services_compose_into_one_transaction(db_session, user):
    """The point of moving commits out of services: a caller can combine several service calls and
    decide once whether they all land. Here the caller changes its mind, and nothing remains."""
    board = board_service.create_board(db_session, user, "Draft", None, default_lists=True)
    card_service.create_card(db_session, user, board.lists[0], "Draft card")
    board_id = board.id
    db_session.rollback()

    assert db_session.get(type(board), board_id) is None


def test_concurrent_modification_becomes_409(client, user, card, monkeypatch):
    """If the version check trips outside update_card's own handling (e.g. two moves of the same
    card), the global handler answers 409 instead of 500."""

    def stale(*_args, **_kwargs):
        raise StaleDataError("UPDATE statement on table 'cards' expected to update 1 row(s); 0 were matched.")

    monkeypatch.setattr(card_service, "move_card", stale)
    response = client.post(
        f"/api/cards/{card['id']}/move", json={"list_id": card["list_id"], "after_id": None}, headers=auth_headers(user)
    )
    assert response.status_code == 409
    assert "reload" in response.json()["detail"]
