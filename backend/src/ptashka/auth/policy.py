"""Who may do what on a board: the permission rules as data and pure functions.

Two kinds of rule:
- Field tables: which board role may change each field of a PATCH. A route admits the lowest role
  in its table (`lowest`), then `missing_role` checks the fields actually sent.
- Person-dependent rules (assigning, comments, leaving a board), which also depend on *who* the
  target is.

Everything here is pure (roles and ids in, answers out); routers turn a "no" into a 403. The
specification lives in tests/test_policy.py as an explicit table, written independently of this
code, so the tests can't just echo the implementation back.
"""

from collections.abc import Iterable, Mapping

from ptashka.models.db import BoardRole

FieldRules = Mapping[str, BoardRole]

VIEWER, CONTRIBUTOR, EDITOR, OWNER = BoardRole.VIEWER, BoardRole.CONTRIBUTOR, BoardRole.EDITOR, BoardRole.OWNER

CARD_FIELDS: FieldRules = {
    "completed": CONTRIBUTOR,  # Working on a card...
    "version": CONTRIBUTOR,  # (not a change: the optimistic-lock check that comes with one)
    "title": EDITOR,  # ...versus managing it.
    "description": EDITOR,
    "due_at": EDITOR,
    "archived": EDITOR,
}

CHECKLIST_ITEM_FIELDS: FieldRules = {
    "done": CONTRIBUTOR,
    "text": EDITOR,
}

BOARD_FIELDS: FieldRules = {
    "name": EDITOR,
    "description": EDITOR,
    "archived": OWNER,
}


def lowest(rules: FieldRules) -> BoardRole:
    """The least a member needs to use the endpoint at all."""
    return min(rules.values(), key=lambda role: role.rank)


def missing_role(role: BoardRole, fields: Iterable[str], rules: FieldRules) -> tuple[BoardRole, list[str]] | None:
    """None if `role` may change all `fields`; otherwise (the role needed, the fields it lacks).

    An unknown field raises KeyError: request schemas only let known fields through, so that would
    be a table that forgot a field, which should fail loudly in tests rather than default to anything.
    """
    denied = sorted(f for f in fields if not role.includes(rules[f]))
    if not denied:
        return None
    return max((rules[f] for f in denied), key=lambda r: r.rank), denied


def can_assign(role: BoardRole, actor_id: int, assignee_id: int) -> bool:
    """Contributors may take (or drop) a card themselves; handing out work is for editors."""
    if actor_id == assignee_id:
        return role.includes(CONTRIBUTOR)
    return role.includes(EDITOR)


def can_edit_comment(actor_id: int, author_id: int | None) -> bool:
    """Only the author: nobody, not even an owner, can put words in someone else's mouth."""
    return author_id is not None and actor_id == author_id


def can_delete_comment(role: BoardRole, actor_id: int, author_id: int | None) -> bool:
    """The author (even if since demoted to viewer), or an owner moderating."""
    return can_edit_comment(actor_id, author_id) or role.includes(OWNER)


def can_remove_member(role: BoardRole, actor_id: int, member_id: int) -> bool:
    """Anyone may leave; only owners remove others. (The last-owner rule is checked separately.)"""
    return actor_id == member_id or role.includes(OWNER)
