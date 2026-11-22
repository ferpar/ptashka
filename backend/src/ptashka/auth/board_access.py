"""Board-level permission dependencies.

Every board-scoped endpoint declares the *minimum* role it needs:

    access: BoardAccess = Depends(board_access(BoardRole.EDITOR))

FastAPI then reads `board_id` from the URL path, authenticates the user, and
checks their BoardMember row before the endpoint runs.

- Not a member → **404**, exactly like a board that doesn't exist, so IDs can't be probed.
- Member, but role too low → **403**: they can already see the board, so nothing leaks.

Site admins get no special access to boards: approving accounts doesn't mean
reading everyone's tasks.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ptashka.auth import policy
from ptashka.auth.dependencies import get_current_user
from ptashka.db.database import DbSession
from ptashka.models.db import Board, BoardList, BoardMember, BoardRole, Card, ChecklistItem, Comment, Label, User


@dataclass
class BoardAccess:
    board: Board
    role: BoardRole
    user: User


@dataclass
class ListAccess:
    board_list: BoardList
    access: BoardAccess


@dataclass
class CardAccess:
    card: Card
    access: BoardAccess


@dataclass
class LabelAccess:
    label: Label
    access: BoardAccess


@dataclass
class ChecklistItemAccess:
    item: ChecklistItem
    access: BoardAccess


@dataclass
class CommentAccess:
    comment: Comment
    access: BoardAccess


def check_fields(role: BoardRole, changes: Iterable[str], rules: policy.FieldRules) -> None:
    """Field-level permissions for PATCH endpoints shared by several roles: the route admits
    `policy.lowest(rules)`, then this refuses (403) any field the caller's role may not change.
    The decision is `policy.missing_role`; this only turns it into HTTP."""
    missing = policy.missing_role(role, changes, rules)
    if missing:
        needed, fields = missing
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires {needed.value} access to change: {', '.join(fields)}",
        )


def _check(db: Session, user: User, board_id: int, minimum: BoardRole) -> BoardAccess:
    row = db.execute(
        select(Board, BoardMember.role)
        .join(BoardMember, BoardMember.board_id == Board.id)
        .where(Board.id == board_id, BoardMember.user_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    board, role = row
    if not role.includes(minimum):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires {minimum.value} access")
    return BoardAccess(board=board, role=role, user=user)


def board_access(minimum: BoardRole) -> Callable[..., BoardAccess]:
    """Dependency for routes with a `{board_id}` path parameter."""

    def dependency(
        db: DbSession,
        board_id: int,  # FastAPI fills this from the path, just like in an endpoint.
        user: User = Depends(get_current_user),
    ) -> BoardAccess:
        return _check(db, user, board_id, minimum)

    return dependency


def _check_child(db: Session, user: User, board_id: int | None, minimum: BoardRole, name: str) -> BoardAccess:
    """Access to something that lives on board `board_id` (None: the thing doesn't exist).
    A missing item and an item on a board you can't see give the *same* 404, so nobody can
    tell whether an id exists on someone else's board."""
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{name} not found")
    if board_id is None:
        raise not_found
    try:
        return _check(db, user, board_id, minimum)
    except HTTPException as e:
        if e.status_code == status.HTTP_404_NOT_FOUND:
            raise not_found
        raise


def list_access(minimum: BoardRole) -> Callable[..., ListAccess]:
    """Dependency for routes with a `{list_id}` path parameter: find the list, then check its board."""

    def dependency(
        db: DbSession,
        list_id: int,
        user: User = Depends(get_current_user),
    ) -> ListAccess:
        board_list = db.get(BoardList, list_id)
        access = _check_child(db, user, board_list.board_id if board_list else None, minimum, "List")
        assert board_list is not None  # _check_child raised otherwise; this tells the type checker.
        return ListAccess(board_list=board_list, access=access)

    return dependency


def card_access(minimum: BoardRole) -> Callable[..., CardAccess]:
    """Dependency for routes with a `{card_id}` path parameter."""

    def dependency(
        db: DbSession,
        card_id: int,
        user: User = Depends(get_current_user),
    ) -> CardAccess:
        card = db.get(Card, card_id)
        access = _check_child(db, user, card.board_id if card else None, minimum, "Card")
        assert card is not None
        return CardAccess(card=card, access=access)

    return dependency


def label_access(minimum: BoardRole) -> Callable[..., LabelAccess]:
    """Dependency for routes with a `{label_id}` path parameter."""

    def dependency(
        db: DbSession,
        label_id: int,
        user: User = Depends(get_current_user),
    ) -> LabelAccess:
        label = db.get(Label, label_id)
        access = _check_child(db, user, label.board_id if label else None, minimum, "Label")
        assert label is not None
        return LabelAccess(label=label, access=access)

    return dependency


def checklist_item_access(minimum: BoardRole) -> Callable[..., ChecklistItemAccess]:
    """Dependency for routes with an `{item_id}` path parameter. Items reach their board via the card."""

    def dependency(
        db: DbSession,
        item_id: int,
        user: User = Depends(get_current_user),
    ) -> ChecklistItemAccess:
        item = db.get(ChecklistItem, item_id)
        access = _check_child(db, user, item.card.board_id if item else None, minimum, "Checklist item")
        assert item is not None
        return ChecklistItemAccess(item=item, access=access)

    return dependency


def comment_access(minimum: BoardRole) -> Callable[..., CommentAccess]:
    """Dependency for routes with a `{comment_id}` path parameter."""

    def dependency(
        db: DbSession,
        comment_id: int,
        user: User = Depends(get_current_user),
    ) -> CommentAccess:
        comment = db.get(Comment, comment_id)
        board_id = db.scalar(select(Card.board_id).where(Card.id == comment.card_id)) if comment else None
        access = _check_child(db, user, board_id, minimum, "Comment")
        assert comment is not None
        return CommentAccess(comment=comment, access=access)

    return dependency
