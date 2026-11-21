"""The MCP tools, end to end through the real API."""

from typing import Any

import pytest
from mcp import Client
from sqlalchemy.orm import Session

from ptashka.models.db import BoardRole, LabelColor, TokenScope
from ptashka.services import board_service, card_service, checklist_service, label_service
from tests.conftest import connect, make_user, token_for

READ_TOOLS = {"whoami", "get_board", "search_cards", "get_card", "whats_new"}
WRITE_TOOLS = {"create_card", "update_card", "move_card", "assign_card", "label_card", "add_comment", "add_checklist_item", "check_item"}


async def call(client: Client, tool: str, **args: Any) -> dict[str, Any]:
    result = await client.call_tool(tool, args)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return result.structured_content


async def error_of(client: Client, tool: str, **args: Any) -> str:
    """The message an agent would read when the call fails."""
    result = await client.call_tool(tool, args)
    assert result.is_error, result.structured_content
    return " ".join(getattr(c, "text", "") for c in result.content)


@pytest.fixture
def world(db: Session) -> dict[str, Any]:
    """A board owned by Olena, with an agent added as contributor and a few cards."""
    owner, agent = make_user(db, "Olena"), make_user(db, "Agent")
    board = board_service.create_board(db, owner, "Home", None, default_lists=True)
    board_service.add_member(db, owner, board, agent.email, BoardRole.CONTRIBUTOR)
    todo, doing, done = board.lists
    report = card_service.create_card(db, owner, todo, "Write the report")
    card_service.create_card(db, owner, todo, "Unassigned chore")
    card_service.assign(db, owner, report, agent.id)
    label_service.create_label(db, board, "urgent", LabelColor.RED)
    label_service.attach(db, owner, report, board.labels[0].id)
    checklist_service.add_item(db, owner, report, "Gather numbers")
    db.commit()
    return {"owner": owner, "agent": agent, "board": board, "todo": todo, "doing": doing, "done": done, "report": report}


# ── Discovery ──


async def test_tools_and_their_hints(db: Session, world: dict[str, Any]) -> None:
    async with connect(token_for(db, world["agent"])) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == READ_TOOLS | WRITE_TOOLS
    read_only = {name: (t.annotations.read_only_hint if t.annotations else None) for name, t in tools.items()}
    assert all(read_only[n] is True for n in READ_TOOLS)
    assert all(read_only[n] is False for n in WRITE_TOOLS)
    # Parameter descriptions reach the agent through the input schema.
    assert "done list" in (tools["move_card"].description or "")
    assert tools["move_card"].input_schema["properties"]["after_card_id"]["description"].startswith("Place it right after")


async def test_read_only_mode_hides_write_tools(db: Session, world: dict[str, Any]) -> None:
    async with connect(token_for(db, world["agent"], TokenScope.READ), read_only=True) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert names == READ_TOOLS


# ── Reading ──


async def test_whoami_and_board(db: Session, world: dict[str, Any]) -> None:
    async with connect(token_for(db, world["agent"])) as client:
        me = await call(client, "whoami")
        board = await call(client, "get_board", board_id=world["board"].id)

    assert me["user"]["name"] == "Agent"
    assert me["boards"] == [{"id": world["board"].id, "name": "Home", "your_role": "contributor"}]
    assert [lst["name"] for lst in board["lists"]] == ["To do", "Doing", "Done"]
    assert board["lists"][2]["is_done_list"] is True
    report = board["lists"][0]["cards"][0]
    # Names resolved, not bare ids.
    assert report == {"id": world["report"].id, "title": "Write the report", "labels": ["urgent"], "assignees": ["Agent"], "checklist": "0/1"}


async def test_search_defaults_to_my_open_tasks(db: Session, world: dict[str, Any]) -> None:
    async with connect(token_for(db, world["agent"])) as client:
        mine = await call(client, "search_cards")
        everyone = await call(client, "search_cards", assignee=None)
    assert [(c["title"], c["board"], c["list"]) for c in mine["cards"]] == [("Write the report", "Home", "To do")]
    assert len(everyone["cards"]) == 2


async def test_get_card_has_what_an_agent_needs(db: Session, world: dict[str, Any]) -> None:
    async with connect(token_for(db, world["agent"])) as client:
        card = await call(client, "get_card", card_id=world["report"].id)
    assert card["version"] == 1
    assert card["list"] == "To do" and card["board"] == "Home"
    assert [(i["text"], i["done"]) for i in card["checklist_items"]] == [("Gather numbers", False)]
    assert any("Olena added “Write the report” to To do" in h for h in card["history"])


# ── A contributor agent's workflow ──


async def test_agent_works_a_task_end_to_end(db: Session, world: dict[str, Any]) -> None:
    report, doing, done = world["report"], world["doing"], world["done"]
    async with connect(token_for(db, world["agent"])) as client:
        start = (await call(client, "whats_new"))["next_since"]

        await call(client, "move_card", card_id=report.id, list_id=doing.id)
        item = (await call(client, "get_card", card_id=report.id))["checklist_items"][0]
        await call(client, "check_item", item_id=item["id"])
        await call(client, "add_comment", card_id=report.id, body="Numbers gathered, report drafted.")
        moved = await call(client, "move_card", card_id=report.id, list_id=done.id)
        assert moved["completed"] is True  # The server's done-list rule.

        news = await call(client, "whats_new", since=start)

    assert [e["what"] for e in news["entries"]] == [
        "Agent moved “Write the report” from To do to Doing",
        "Agent checked “Gather numbers” on “Write the report”",
        "Agent commented on “Write the report”: “Numbers gathered, report drafted.”",
        "Agent moved “Write the report” from Doing to Done",
        "Agent completed “Write the report”",
    ]
    assert news["next_since"] > start


async def test_contributor_can_take_a_card_but_not_assign_others(db: Session, world: dict[str, Any]) -> None:
    chore = world["todo"].cards[1]
    async with connect(token_for(db, world["agent"])) as client:
        assert (await call(client, "assign_card", card_id=chore.id))["assigned"] is True
        message = await error_of(client, "assign_card", card_id=chore.id, user_id=world["owner"].id)
    assert "Contributors can only assign themselves" in message


# ── Errors an agent can act on ──


async def test_role_limits_are_explained(db: Session, world: dict[str, Any]) -> None:
    async with connect(token_for(db, world["agent"])) as client:
        message = await error_of(client, "update_card", card_id=world["report"].id, title="Rewritten")
    assert "Not allowed: Requires editor access to change: title" in message  # (The SDK prefixes "Error executing tool …:")


async def test_version_conflicts_say_how_to_recover(db: Session, world: dict[str, Any]) -> None:
    async with connect(token_for(db, world["owner"])) as client:
        await call(client, "update_card", card_id=world["report"].id, title="v2", version=1)
        message = await error_of(client, "update_card", card_id=world["report"].id, title="v3", version=1)
    assert "call get_card for the latest version, then retry" in message


async def test_read_only_tokens_are_explained(db: Session, world: dict[str, Any]) -> None:
    async with connect(token_for(db, world["agent"], TokenScope.READ)) as client:  # All tools registered.
        message = await error_of(client, "move_card", card_id=world["report"].id, list_id=world["doing"].id)
    assert "read-only" in message


async def test_unknown_labels_list_the_alternatives(db: Session, world: dict[str, Any]) -> None:
    async with connect(token_for(db, world["owner"])) as client:
        message = await error_of(client, "label_card", card_id=world["report"].id, label="blocked")
        added = await call(client, "label_card", card_id=world["report"].id, label="URGENT", on=False)
    assert "Available: urgent" in message
    assert added == {"card_id": world["report"].id, "label": "urgent", "on": False}


async def test_bad_tokens_and_empty_updates(db: Session, world: dict[str, Any]) -> None:
    async with connect("ptk_not-a-real-token") as client:
        assert "Authentication failed" in await error_of(client, "whoami")
    async with connect(token_for(db, world["owner"])) as client:
        assert "Nothing to change" in await error_of(client, "update_card", card_id=world["report"].id, version=1)


async def test_other_peoples_boards_look_missing(db: Session, world: dict[str, Any]) -> None:
    stranger = make_user(db, "Stranger")
    async with connect(token_for(db, stranger)) as client:
        message = await error_of(client, "get_board", board_id=world["board"].id)
    assert "Board not found" in message and "aren't a member" in message
