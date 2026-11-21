"""ptashka's MCP server: tools for agents that track and work on tasks.

Run it with an API token (create one on ptashka's "API tokens" page, or with
`python -m ptashka.cli.create_token` on the server):

    PTASHKA_URL=http://localhost:8020 PTASHKA_TOKEN=ptk_... ptashka-mcp

PTASHKA_READ_ONLY=1 registers only the read tools: the agent never even sees the others.

The tools are designed for agents doing task work, not as a mirror of the REST API: compact output
with names resolved, errors that say what to do next, and deliberately no way to delete anything
(archiving, which is reversible, is as far as it goes).
"""

import logging
import os
import sys
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from ptashka_mcp import views
from ptashka_mcp.api import PtashkaApi

Json = dict[str, Any]

INSTRUCTIONS = """\
ptashka is a Trello-like task tracker: boards contain lists ("To do", "Doing", "Done"...), lists contain cards (tasks).
- Start with `whoami` (your boards and role) or `search_cards` (e.g. your open tasks across all boards).
- Ids come from `get_board`, `search_cards` and `get_card`; pass them to the other tools.
- Each board has at most one *done list*: moving a card into it completes the card, moving it out reopens it.
- Roles: viewer (read only), contributor (move, complete, tick checklist items, comment, assign yourself),
  editor (also create and edit cards), owner. Errors say when your role doesn't allow something.
- When editing a card you read earlier, pass its `version` to `update_card`, so you never overwrite
  someone else's newer change. On a conflict, re-read with `get_card` and retry.
- To follow what happens, call `whats_new` with the `next_since` it returned last time.
"""

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
WRITE_IDEMPOTENT = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

CardId = Annotated[int, Field(description="The card's id (from get_board, search_cards or get_card)")]


def build_server(api: PtashkaApi, read_only: bool = False) -> MCPServer:
    server = MCPServer("ptashka", instructions=INSTRUCTIONS)

    async def board_of(card_id: int) -> tuple[Json, Json]:
        card = await api.get(f"/api/cards/{card_id}")
        return card, await api.get(f"/api/boards/{card['board_id']}")

    # ── Reading ──

    @server.tool(annotations=READ)
    async def whoami() -> Json:
        """Who this token acts as, and the boards they can see with their role on each."""
        me = await api.get("/api/auth/me")
        boards = (await api.get("/api/boards"))["boards"]
        return {
            "user": {"id": me["id"], "name": me["display_name"], "email": me["email"]},
            "boards": [{"id": b["id"], "name": b["name"], "your_role": b["my_role"]} for b in boards],
        }

    @server.tool(annotations=READ)
    async def get_board(
        board_id: int,
        include_archived: Annotated[bool, Field(description="Also show archived lists and cards")] = False,
    ) -> Json:
        """A board: its lists in order, each with its cards (labels, assignees, due date, checklist
        progress, comment count), plus the board's members and labels."""
        return views.board_view(await api.get(f"/api/boards/{board_id}", include_archived=include_archived))

    @server.tool(annotations=READ)
    async def search_cards(
        assignee: Annotated[str | None, Field(description='"me", a user id, or omit for anyone')] = "me",
        completed: Annotated[bool | None, Field(description="false: open cards (default); true: completed; null: both")] = False,
        board_id: Annotated[int | None, Field(description="Only this board")] = None,
        label: Annotated[str | None, Field(description="Label name, matched on every board (case-insensitive)")] = None,
        text: Annotated[str | None, Field(description="Words in the title or description")] = None,
        overdue: Annotated[bool, Field(description="Only cards past their due date and not completed")] = False,
        due_before: Annotated[str | None, Field(description="ISO 8601 with timezone, e.g. 2026-12-01T00:00:00Z")] = None,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> Json:
        """Search cards across every board you belong to. By default: your open tasks.
        Sorted by due date (soonest first, undated last)."""
        result = await api.get(
            "/api/cards",
            assignee=assignee, completed=completed, board_id=board_id, label=label, q=text,
            overdue=overdue or None, due_before=due_before, limit=limit,
        )
        return {"cards": [views.search_hit(h) for h in result["cards"]], "more": result["next_offset"] is not None}

    @server.tool(annotations=READ)
    async def get_card(card_id: CardId) -> Json:
        """Everything about one card: description, checklist items (with ids), recent comments,
        recent history, and its current `version` (pass it to update_card)."""
        card, board = await board_of(card_id)
        comments = (await api.get(f"/api/cards/{card_id}/comments"))["comments"]
        history = (await api.get(f"/api/cards/{card_id}/activity", limit=10))["activities"]
        return views.card_detail(card, board, comments, history)

    @server.tool(annotations=READ)
    async def whats_new(
        since: Annotated[int, Field(ge=0, description="The next_since from your previous call; 0 for everything")] = 0,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> Json:
        """What happened on your boards after entry `since`, oldest first, as readable sentences.
        Keep `next_since` and pass it next time to get only what's new. Entries appear a few
        seconds after they happen (so one is never skipped)."""
        result = await api.get("/api/activity", since=since, limit=limit)
        return {"entries": [views.feed_entry(e) for e in result["activities"]], "next_since": result["next_since"]}

    if read_only:
        return server

    # ── Working on tasks ──

    @server.tool(annotations=WRITE)
    async def create_card(
        list_id: Annotated[int, Field(description="The list to add it to (ids from get_board)")],
        title: Annotated[str, Field(min_length=1, max_length=200)],
        description: Annotated[str | None, Field(max_length=20000, description="Markdown")] = None,
        due_at: Annotated[str | None, Field(description="ISO 8601 with timezone, e.g. 2026-12-01T17:00:00+01:00")] = None,
    ) -> Json:
        """Add a card at the bottom of a list (needs editor role). A card created in the done list starts completed."""
        card = await api.post(f"/api/lists/{list_id}/cards", {"title": title, "description": description, "due_at": due_at})
        return {"id": card["id"], "title": card["title"], "list_id": card["list_id"], "version": card["version"]}

    @server.tool(annotations=WRITE_IDEMPOTENT)
    async def update_card(
        card_id: CardId,
        title: Annotated[str | None, Field(min_length=1, max_length=200)] = None,
        description: Annotated[str | None, Field(max_length=20000, description='Markdown; "" clears it')] = None,
        due_at: Annotated[str | None, Field(description='ISO 8601 with timezone; "" clears the due date')] = None,
        completed: Annotated[bool | None, Field(description="Complete (true) or reopen (false) without moving it")] = None,
        archived: Annotated[bool | None, Field(description="Archive (true, hides it; reversible) or restore (false)")] = None,
        version: Annotated[int | None, Field(description="The version you read (get_card); refuses to overwrite a newer change")] = None,
    ) -> Json:
        """Change a card. Only the fields you pass change. Contributors may only set `completed`;
        everything else needs the editor role."""
        body: Json = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description or None
        if due_at is not None:
            body["due_at"] = due_at or None
        if completed is not None:
            body["completed"] = completed
        if archived is not None:
            body["archived"] = archived
        if version is not None:
            body["version"] = version
        if not body or body.keys() == {"version"}:
            raise ToolError("Nothing to change: pass at least one of title, description, due_at, completed, archived.")
        card = await api.patch(f"/api/cards/{card_id}", body)
        return {"id": card["id"], "title": card["title"], "completed": card["completed_at"] is not None, "version": card["version"]}

    @server.tool(annotations=WRITE_IDEMPOTENT)
    async def move_card(
        card_id: CardId,
        list_id: Annotated[int, Field(description="Target list on the same board (ids from get_board)")],
        after_card_id: Annotated[int | None, Field(description="Place it right after this card; omit for the top of the list")] = None,
    ) -> Json:
        """Move a card to another list (or reorder it). Moving into the board's done list completes it;
        moving out of it reopens it. Contributors can do this."""
        card = await api.post(f"/api/cards/{card_id}/move", {"list_id": list_id, "after_id": after_card_id})
        return {"id": card["id"], "list_id": card["list_id"], "completed": card["completed_at"] is not None, "version": card["version"]}

    @server.tool(annotations=WRITE_IDEMPOTENT)
    async def assign_card(
        card_id: CardId,
        user_id: Annotated[int | None, Field(description="A board member's id (from get_board); omit for yourself")] = None,
        assigned: Annotated[bool, Field(description="true to assign, false to unassign")] = True,
    ) -> Json:
        """Assign someone to a card (or unassign). Contributors may only assign or unassign themselves."""
        target = user_id if user_id is not None else (await api.get("/api/auth/me"))["id"]
        path = f"/api/cards/{card_id}/assignees/{target}"
        await (api.put(path) if assigned else api.delete(path))
        return {"card_id": card_id, "user_id": target, "assigned": assigned}

    @server.tool(annotations=WRITE_IDEMPOTENT)
    async def label_card(
        card_id: CardId,
        label: Annotated[str, Field(description="The label's name (case-insensitive) or id, from the card's board")],
        on: Annotated[bool, Field(description="true to add, false to remove")] = True,
    ) -> Json:
        """Add or remove a label on a card (editor role)."""
        _, board = await board_of(card_id)
        match = next(
            (lb for lb in board["labels"] if lb["name"].lower() == label.strip().lower() or str(lb["id"]) == label.strip()),
            None,
        )
        if match is None:
            available = ", ".join(lb["name"] for lb in board["labels"]) or "none"
            raise ToolError(f"No label “{label}” on board “{board['name']}”. Available: {available}.")
        path = f"/api/cards/{card_id}/labels/{match['id']}"
        await (api.put(path) if on else api.delete(path))
        return {"card_id": card_id, "label": match["name"], "on": on}

    @server.tool(annotations=WRITE)
    async def add_comment(card_id: CardId, body: Annotated[str, Field(min_length=1, max_length=10000, description="Markdown")]) -> Json:
        """Comment on a card, e.g. to report progress or ask a question. Contributors can do this."""
        comment = await api.post(f"/api/cards/{card_id}/comments", {"body": body})
        return {"comment_id": comment["id"], "card_id": card_id}

    @server.tool(annotations=WRITE)
    async def add_checklist_item(card_id: CardId, text: Annotated[str, Field(min_length=1, max_length=500)]) -> Json:
        """Add an item at the end of a card's checklist (editor role)."""
        item = await api.post(f"/api/cards/{card_id}/checklist", {"text": text})
        return {"item_id": item["id"], "text": item["text"]}

    @server.tool(annotations=WRITE_IDEMPOTENT)
    async def check_item(
        item_id: Annotated[int, Field(description="Checklist item id (from get_card)")],
        done: Annotated[bool, Field(description="true to tick, false to untick")] = True,
    ) -> Json:
        """Tick or untick a checklist item. Contributors can do this."""
        item = await api.patch(f"/api/checklist-items/{item_id}", {"done": done})
        return {"item_id": item["id"], "text": item["text"], "done": item["done_at"] is not None}

    return server


def main() -> None:
    token = os.getenv("PTASHKA_TOKEN")
    if not token:
        # stdout carries the MCP protocol; anything for humans goes to stderr.
        print("PTASHKA_TOKEN is not set: create an API token in ptashka and pass it in the environment.", file=sys.stderr)
        sys.exit(2)
    # httpx logs every request at INFO; on stderr that floods the client's MCP logs (and URLs can
    # carry search text). Warnings and errors still come through.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    api = PtashkaApi(os.getenv("PTASHKA_URL", "http://localhost:8020"), token)
    read_only = os.getenv("PTASHKA_READ_ONLY", "").lower() in {"1", "true", "yes"}
    build_server(api, read_only=read_only).run("stdio")


if __name__ == "__main__":
    main()
