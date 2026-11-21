"""Compact, agent-friendly views of API data.

Agents read every byte a tool returns, so these keep only what helps decide what to do next, and
resolve ids to names (labels, assignees, lists) while keeping the ids needed for follow-up calls.
"""

from typing import Any

Json = dict[str, Any]


def _names(board: Json) -> tuple[dict[int, str], dict[int, str]]:
    members = {m["user"]["id"]: m["user"]["display_name"] for m in board["members"]}
    labels = {label["id"]: label["name"] for label in board["labels"]}
    return members, labels


def card_summary(card: Json, members: dict[int, str], labels: dict[int, str]) -> Json:
    view: Json = {"id": card["id"], "title": card["title"]}
    if card.get("completed_at"):
        view["completed"] = True
    if card.get("archived_at"):
        view["archived"] = True
    if card.get("due_at"):
        view["due"] = card["due_at"]
    if card["label_ids"]:
        view["labels"] = [labels.get(i, f"#{i}") for i in card["label_ids"]]
    if card["assignee_ids"]:
        view["assignees"] = [members.get(i, f"user {i}") for i in card["assignee_ids"]]
    if card["checklist_total"]:
        view["checklist"] = f"{card['checklist_done']}/{card['checklist_total']}"
    if card["comment_count"]:
        view["comments"] = card["comment_count"]
    return view


def board_view(board: Json) -> Json:
    members, labels = _names(board)
    return {
        "id": board["id"],
        "name": board["name"],
        "your_role": board["my_role"],
        "lists": [
            {
                "id": lst["id"],
                "name": lst["name"],
                **({"is_done_list": True} if lst["is_done"] else {}),
                "cards": [card_summary(c, members, labels) for c in lst["cards"]],
            }
            for lst in board["lists"]
        ],
        "members": [{"id": m["user"]["id"], "name": m["user"]["display_name"], "role": m["role"]} for m in board["members"]],
        "labels": [{"id": label["id"], "name": label["name"]} for label in board["labels"]],
    }


def search_hit(hit: Json) -> Json:
    view = card_summary(hit, {}, {})
    # Search results span boards, so names aren't resolvable here; show where the card lives instead.
    view.pop("labels", None)
    view.pop("assignees", None)
    return {**view, "board_id": hit["board_id"], "board": hit["board_name"], "list": hit["list_name"]}


def card_detail(card: Json, board: Json, comments: list[Json], history: list[Json]) -> Json:
    members, labels = _names(board)
    list_name = next((lst["name"] for lst in board["lists"] if lst["id"] == card["list_id"]), None)
    return {
        **card_summary(card, members, labels),
        "version": card["version"],  # Pass back to update_card to avoid overwriting someone else's edit.
        "board_id": card["board_id"],
        "board": board["name"],
        "list_id": card["list_id"],
        "list": list_name,
        "description": card["description"],
        "checklist_items": [{"id": i["id"], "text": i["text"], "done": i["done_at"] is not None} for i in card["checklist"]],
        "recent_comments": [
            {"author": (c["author"] or {}).get("display_name", "deleted user"), "at": c["created_at"], "body": c["body"]}
            for c in comments[-10:]
        ],
        "history": [f"{entry['created_at']}: {describe(entry)}" for entry in history[:10]],
    }


def describe(entry: Json) -> str:
    """One activity entry as a sentence, starting with who did it."""
    d = entry["data"]
    who = (entry.get("actor") or {}).get("display_name", "Someone")
    card = f"“{d.get('card_title', '')}”"
    kind = entry["kind"]
    text = {
        "board.created": "created the board",
        "board.updated": f"updated the board ({', '.join(d.get('changed', []))})",
        "board.archived": "archived the board",
        "board.restored": "restored the board",
        "member.added": f"added {d.get('user_name')} as {d.get('role')}",
        "member.role_changed": f"made {d.get('user_name')} {d.get('to_role')} (was {d.get('from_role')})",
        "member.removed": "left the board" if d.get("left") else f"removed {d.get('user_name')}",
        "list.created": f"added list “{d.get('list_name')}”",
        "list.updated": f"renamed a list to “{(d.get('to') or {}).get('name')}”",
        "list.moved": f"moved list “{d.get('list_name')}”",
        "list.archived": f"archived list “{d.get('list_name')}”",
        "list.restored": f"restored list “{d.get('list_name')}”",
        "list.set_done": f"made “{d.get('list_name')}” the done list" if d.get("is_done") else f"unset “{d.get('list_name')}” as done list",
        "card.created": f"added {card} to {d.get('list_name')}",
        "card.updated": f"edited {card} ({', '.join(d.get('changed', []))})",
        "card.moved": f"moved {card} from {d.get('from_list')} to {d.get('to_list')}",
        "card.completed": f"completed {card}",
        "card.reopened": f"reopened {card}",
        "card.archived": f"archived {card}",
        "card.restored": f"restored {card}",
        "card.deleted": f"deleted {card}",
        "label.added": f"labelled {card} “{d.get('label_name')}”",
        "label.removed": f"removed label “{d.get('label_name')}” from {card}",
        "assignee.added": f"assigned {d.get('user_name')} to {card}",
        "assignee.removed": f"unassigned {d.get('user_name')} from {card}",
        "checklist.added": f"added “{d.get('text')}” to the checklist of {card}",
        "checklist.checked": f"checked “{d.get('text')}” on {card}",
        "checklist.unchecked": f"unchecked “{d.get('text')}” on {card}",
        "comment.added": f"commented on {card}: “{d.get('excerpt')}”",
    }.get(kind, kind)  # An unknown (newer) kind still reads as its name.
    return f"{who} {text}"


def feed_entry(entry: Json) -> Json:
    return {
        "id": entry["id"],
        "board_id": entry["board_id"],
        "card_id": entry["card_id"],
        "at": entry["created_at"],
        "what": describe(entry),
    }
