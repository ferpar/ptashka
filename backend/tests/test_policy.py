"""Unit tests for auth/policy.py: pure, no database or HTTP, microseconds each.

The expected behaviour is written out below as explicit tables (the specification), *not* derived
from policy.CARD_FIELDS & co. A test that looped over the policy's own tables would only check the
code against itself and pass whatever the tables said.

test_roles.py still checks the same rules end to end through the API (the wiring); these check
every combination of the rules themselves, which would be slow and verbose through HTTP.
"""

import pytest

from ptashka.auth import policy
from ptashka.models.db import BoardRole

ROLES = [BoardRole.VIEWER, BoardRole.CONTRIBUTOR, BoardRole.EDITOR, BoardRole.OWNER]
Y, N = True, False

# Who may change which field.          viewer  contributor  editor  owner
CARD_SPEC = {
    "completed":                        (N,     Y,           Y,      Y),
    "version":                          (N,     Y,           Y,      Y),
    "title":                            (N,     N,           Y,      Y),
    "description":                      (N,     N,           Y,      Y),
    "due_at":                           (N,     N,           Y,      Y),
    "archived":                         (N,     N,           Y,      Y),
}
CHECKLIST_SPEC = {
    "done":                             (N,     Y,           Y,      Y),
    "text":                             (N,     N,           Y,      Y),
}
BOARD_SPEC = {
    "name":                             (N,     N,           Y,      Y),
    "description":                      (N,     N,           Y,      Y),
    "archived":                         (N,     N,           N,      Y),
}

FIELD_CASES = [
    pytest.param(rules, field, role, allowed, id=f"{name}.{field}-{role.value}")
    for name, rules, spec in [
        ("card", policy.CARD_FIELDS, CARD_SPEC),
        ("checklist", policy.CHECKLIST_ITEM_FIELDS, CHECKLIST_SPEC),
        ("board", policy.BOARD_FIELDS, BOARD_SPEC),
    ]
    for field, row in spec.items()
    for role, allowed in zip(ROLES, row)
]


@pytest.mark.parametrize("rules, field, role, allowed", FIELD_CASES)
def test_field_permissions(rules, field, role, allowed):
    assert (policy.missing_role(role, [field], rules) is None) is allowed


@pytest.mark.parametrize(
    "rules, spec",
    [(policy.CARD_FIELDS, CARD_SPEC), (policy.CHECKLIST_ITEM_FIELDS, CHECKLIST_SPEC), (policy.BOARD_FIELDS, BOARD_SPEC)],
)
def test_every_field_is_specified(rules, spec):
    """A field added to the policy must also be added to the specification above (and vice versa)."""
    assert set(rules) == set(spec)


def test_routes_admit_the_lowest_role_in_their_table():
    assert policy.lowest(policy.CARD_FIELDS) == BoardRole.CONTRIBUTOR
    assert policy.lowest(policy.CHECKLIST_ITEM_FIELDS) == BoardRole.CONTRIBUTOR
    assert policy.lowest(policy.BOARD_FIELDS) == BoardRole.EDITOR


def test_missing_role_names_the_role_needed_and_the_fields():
    # A contributor completing a card and renaming it in one request: the rename needs editor.
    assert policy.missing_role(BoardRole.CONTRIBUTOR, ["completed", "title", "due_at"], policy.CARD_FIELDS) == (
        BoardRole.EDITOR,
        ["due_at", "title"],
    )
    # An editor archiving a board: the highest role among the denied fields.
    assert policy.missing_role(BoardRole.EDITOR, ["name", "archived"], policy.BOARD_FIELDS) == (BoardRole.OWNER, ["archived"])
    assert policy.missing_role(BoardRole.EDITOR, [], policy.CARD_FIELDS) is None


def test_unknown_fields_fail_loudly():
    with pytest.raises(KeyError):
        policy.missing_role(BoardRole.OWNER, ["colour"], policy.CARD_FIELDS)


ME, OTHER = 1, 2

#                    viewer  contributor  editor  owner
ASSIGN_SPEC = {
    "myself":       (N,     Y,           Y,      Y),
    "someone else": (N,     N,           Y,      Y),
}


@pytest.mark.parametrize(
    "target, role, allowed",
    [(t, r, a) for t, row in ASSIGN_SPEC.items() for r, a in zip(ROLES, row)],
)
def test_assigning(target, role, allowed):
    assert policy.can_assign(role, ME, ME if target == "myself" else OTHER) is allowed


#                                   viewer  contributor  editor  owner
REMOVE_MEMBER_SPEC = {
    "leave (remove myself)":       (Y,     Y,           Y,      Y),
    "remove someone else":         (N,     N,           N,      Y),
}


@pytest.mark.parametrize(
    "case, role, allowed",
    [(c, r, a) for c, row in REMOVE_MEMBER_SPEC.items() for r, a in zip(ROLES, row)],
)
def test_removing_members(case, role, allowed):
    target = ME if case.startswith("leave") else OTHER
    assert policy.can_remove_member(role, ME, target) is allowed


#                                   viewer  contributor  editor  owner
DELETE_COMMENT_SPEC = {
    "my own comment":              (Y,     Y,           Y,      Y),  # Even if since demoted to viewer.
    "someone else's":              (N,     N,           N,      Y),  # Owners moderate.
    "from a deleted account":      (N,     N,           N,      Y),
}
AUTHORS = {"my own comment": ME, "someone else's": OTHER, "from a deleted account": None}


@pytest.mark.parametrize(
    "case, role, allowed",
    [(c, r, a) for c, row in DELETE_COMMENT_SPEC.items() for r, a in zip(ROLES, row)],
)
def test_deleting_comments(case, role, allowed):
    assert policy.can_delete_comment(role, ME, AUTHORS[case]) is allowed


@pytest.mark.parametrize(
    "author, allowed",
    [(ME, True), (OTHER, False), (None, False)],
    ids=["my own", "someone else's (even for owners)", "deleted author"],
)
def test_editing_comments(author, allowed):
    assert policy.can_edit_comment(ME, author) is allowed
