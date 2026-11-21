"""Boards, their members and their lists."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ptashka.models.db import ActivityKind, Board, BoardList, BoardMember, BoardRole, Card, User, UserStatus
from ptashka.services import activity_service, locks, ordering
from ptashka.services.auth_service import normalize_email

DEFAULT_LISTS = ("To do", "Doing", "Done")
DONE_LIST = "Done"


class UserNotFoundError(Exception):
    pass


class AlreadyMemberError(Exception):
    pass


class LastOwnerError(Exception):
    """Every board must keep at least one owner, or nobody could manage it."""


class InvalidMoveError(Exception):
    pass


# ── Boards ──


def boards_for_user(db: Session, user: User, include_archived: bool = False) -> list[tuple[Board, BoardRole]]:
    """The boards `user` belongs to, with their role on each, newest first."""
    stmt = (
        select(Board, BoardMember.role)
        .join(BoardMember, BoardMember.board_id == Board.id)
        .where(BoardMember.user_id == user.id)
        .order_by(Board.created_at.desc(), Board.id.desc())
    )
    if not include_archived:
        stmt = stmt.where(Board.archived_at.is_(None))
    return [(board, role) for board, role in db.execute(stmt)]


def load_board_tree(db: Session, board_id: int) -> Board:
    """Load a board with its lists, their cards, and its members' users in a fixed number of queries.

    Without this, reading `board.lists` then each `lst.cards` (and each `member.user`) lazily
    issues one query per list and per member: the N+1 problem. `selectinload` instead runs one
    extra `SELECT ... WHERE parent_id IN (...)` per relationship, however many rows there are.
    """
    stmt = (
        select(Board)
        .where(Board.id == board_id)
        .options(
            # One query per relationship level, however many lists/cards/links there are.
            selectinload(Board.lists)
            .selectinload(BoardList.cards)
            .options(selectinload(Card.label_links), selectinload(Card.assignee_links)),
            selectinload(Board.members).joinedload(BoardMember.user),
            selectinload(Board.labels),
        )
    )
    return db.scalars(stmt).one()


def create_board(db: Session, actor: User, name: str, description: str | None, default_lists: bool) -> Board:
    board = Board(name=name.strip(), description=description, created_by_id=actor.id)
    # Appending to relationship lists adds the rows to the session together with the board.
    board.members.append(BoardMember(user_id=actor.id, role=BoardRole.OWNER))
    if default_lists:
        for list_name, position in zip(DEFAULT_LISTS, ordering.spread(len(DEFAULT_LISTS))):
            board.lists.append(BoardList(name=list_name, position=position, is_done=list_name == DONE_LIST))
    db.add(board)
    db.flush()
    db.refresh(board)
    activity_service.record(db, actor, ActivityKind.BOARD_CREATED, board.id, name=board.name)
    return board


def update_board(db: Session, actor: User, board: Board, changes: dict[str, Any]) -> Board:
    """Apply a PATCH (fields the client sent). Permission checks happen in the router."""
    before = {"name": board.name, "description": board.description}
    if changes.get("name") is not None:
        board.name = changes["name"].strip()
    if "description" in changes:  # null is allowed here: it clears the description.
        board.description = changes["description"]
    if diff := activity_service.changes(before, {"name": board.name, "description": board.description}):
        activity_service.record(db, actor, ActivityKind.BOARD_UPDATED, board.id, **diff)
    if changes.get("archived") is not None and _set_archived(board, changes["archived"]):
        kind = ActivityKind.BOARD_ARCHIVED if changes["archived"] else ActivityKind.BOARD_RESTORED
        activity_service.record(db, actor, kind, board.id)
    db.flush()
    return board


def toggled_timestamp(current: datetime | None, on: bool) -> datetime | None:
    """For "flag stored as a timestamp" columns (archived_at, completed_at):
    turning on keeps an existing timestamp, so re-sending `true` doesn't rewrite history."""
    if not on:
        return None
    return current or datetime.now(timezone.utc)


def _set_archived(item: Board | BoardList, archived: bool) -> bool:
    """Returns whether anything changed (re-archiving an archived item isn't news)."""
    was = item.archived_at is not None
    item.archived_at = toggled_timestamp(item.archived_at, archived)
    return was != archived


# ── Members ──


def _owner_count(db: Session, board_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(BoardMember).where(
            BoardMember.board_id == board_id, BoardMember.role == BoardRole.OWNER
        )
    ) or 0


def _who(user: User) -> dict[str, Any]:
    return {"user_id": user.id, "user_name": user.display_name}


def add_member(db: Session, actor: User, board: Board, email: str, role: BoardRole) -> BoardMember:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    # Pending/disabled accounts are treated as unknown: you can only share with real, active users.
    if user is None or user.status != UserStatus.ACTIVE:
        raise UserNotFoundError("No active user with that email")
    if db.get(BoardMember, (board.id, user.id)):
        raise AlreadyMemberError("User is already a member of this board")
    member = BoardMember(board_id=board.id, user_id=user.id, role=role)
    db.add(member)
    db.flush()
    db.refresh(member)
    activity_service.record(db, actor, ActivityKind.MEMBER_ADDED, board.id, **_who(user), role=role.value)
    return member


def change_member_role(db: Session, actor: User, member: BoardMember, role: BoardRole) -> BoardMember:
    if member.role == BoardRole.OWNER and role != BoardRole.OWNER and _owner_count(db, member.board_id) == 1:
        raise LastOwnerError("A board needs at least one owner")
    if role != member.role:
        activity_service.record(
            db, actor, ActivityKind.MEMBER_ROLE_CHANGED, member.board_id,
            **_who(member.user), from_role=member.role.value, to_role=role.value,
        )
        member.role = role
    db.flush()
    db.refresh(member)
    return member


def remove_member(db: Session, actor: User, member: BoardMember) -> None:
    if member.role == BoardRole.OWNER and _owner_count(db, member.board_id) == 1:
        raise LastOwnerError("A board needs at least one owner")
    activity_service.record(
        db, actor, ActivityKind.MEMBER_REMOVED, member.board_id, **_who(member.user), left=member.user_id == actor.id
    )
    db.delete(member)
    db.flush()


# ── Lists ──


def _ordered_lists(db: Session, board_id: int, exclude_id: int | None = None) -> list[BoardList]:
    # Archived lists are included: they keep their slot and reappear there when restored.
    stmt = select(BoardList).where(BoardList.board_id == board_id).order_by(BoardList.position, BoardList.id)
    if exclude_id is not None:
        stmt = stmt.where(BoardList.id != exclude_id)
    return list(db.scalars(stmt))


def _about(board_list: BoardList) -> dict[str, Any]:
    return {"list_id": board_list.id, "list_name": board_list.name}


def create_list(db: Session, actor: User, board: Board, name: str) -> BoardList:
    """New lists go at the end of the board."""
    locks.lock(db, Board, board.id)
    siblings = _ordered_lists(db, board.id)
    board_list = BoardList(board_id=board.id, name=name.strip(), position=ordering.place(siblings, len(siblings)))
    db.add(board_list)
    db.flush()
    db.refresh(board_list)
    activity_service.record(db, actor, ActivityKind.LIST_CREATED, board.id, **_about(board_list))
    return board_list


def update_list(db: Session, actor: User, board_list: BoardList, changes: dict[str, Any]) -> BoardList:
    """Rename, archive/restore, or make it the board's done list (fields the client sent)."""
    if changes.get("name") is not None:
        before = {"name": board_list.name}
        board_list.name = changes["name"].strip()
        if diff := activity_service.changes(before, {"name": board_list.name}):
            activity_service.record(db, actor, ActivityKind.LIST_UPDATED, board_list.board_id, list_id=board_list.id, **diff)
    if changes.get("archived") is not None and _set_archived(board_list, changes["archived"]):
        kind = ActivityKind.LIST_ARCHIVED if changes["archived"] else ActivityKind.LIST_RESTORED
        activity_service.record(db, actor, kind, board_list.board_id, **_about(board_list))
    if changes.get("is_done") is not None and changes["is_done"] != board_list.is_done:
        _set_done_list(db, board_list, changes["is_done"])
        activity_service.record(
            db, actor, ActivityKind.LIST_SET_DONE, board_list.board_id, **_about(board_list), is_done=changes["is_done"]
        )
    db.flush()
    db.refresh(board_list)
    return board_list


def _set_done_list(db: Session, board_list: BoardList, is_done: bool) -> None:
    """Make `board_list` the board's done list (replacing any other), or a regular list again.

    Only affects future moves: cards already in the list keep their completion state.
    """
    if is_done:
        locks.lock(db, Board, board_list.board_id)  # Two requests picking different done lists take turns.
        for other in db.scalars(
            select(BoardList).where(
                BoardList.board_id == board_list.board_id, BoardList.is_done, BoardList.id != board_list.id
            )
        ):
            other.is_done = False
        # Send the "unset" UPDATEs before the "set" one: otherwise the partial unique index could
        # briefly see two done lists on the board and reject the change.
        db.flush()
    board_list.is_done = is_done


def move_list(db: Session, actor: User, board_list: BoardList, after_id: int | None) -> BoardList:
    """Put `board_list` right after list `after_id` (None = first)."""
    if after_id == board_list.id:
        raise InvalidMoveError("A list can't be placed after itself")
    locks.lock(db, Board, board_list.board_id)
    siblings = _ordered_lists(db, board_list.board_id, exclude_id=board_list.id)
    try:
        index = ordering.index_after([s.id for s in siblings], after_id)
    except ValueError:
        # Also covers a list on another board: you can't reference what isn't here.
        raise InvalidMoveError("after_id is not a list on this board")
    old_position = board_list.position
    board_list.position = ordering.place(siblings, index)
    if board_list.position != old_position:
        activity_service.record(db, actor, ActivityKind.LIST_MOVED, board_list.board_id, **_about(board_list))
    db.flush()
    db.refresh(board_list)
    return board_list
