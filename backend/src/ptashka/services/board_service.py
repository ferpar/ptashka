"""Boards, their members and their lists."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ptashka.models.db import Board, BoardList, BoardMember, BoardRole, User, UserStatus
from ptashka.services import ordering
from ptashka.services.auth_service import normalize_email

DEFAULT_LISTS = ("To do", "Doing", "Done")


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


def create_board(db: Session, creator: User, name: str, description: str | None, default_lists: bool) -> Board:
    board = Board(name=name.strip(), description=description, created_by_id=creator.id)
    # Appending to relationship lists adds the rows to the session together with the board.
    board.members.append(BoardMember(user_id=creator.id, role=BoardRole.OWNER))
    if default_lists:
        for name, position in zip(DEFAULT_LISTS, ordering.spread(len(DEFAULT_LISTS))):
            board.lists.append(BoardList(name=name, position=position))
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


def set_archived(board_or_list: Board | BoardList, archived: bool) -> None:
    if archived and board_or_list.archived_at is None:
        board_or_list.archived_at = datetime.now(timezone.utc)
    elif not archived:
        board_or_list.archived_at = None


# ── Members ──


def _owner_count(db: Session, board_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(BoardMember).where(
            BoardMember.board_id == board_id, BoardMember.role == BoardRole.OWNER
        )
    ) or 0


def add_member(db: Session, board: Board, email: str, role: BoardRole) -> BoardMember:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    # Pending/disabled accounts are treated as unknown: you can only share with real, active users.
    if user is None or user.status != UserStatus.ACTIVE:
        raise UserNotFoundError("No active user with that email")
    if db.get(BoardMember, (board.id, user.id)):
        raise AlreadyMemberError("User is already a member of this board")
    member = BoardMember(board_id=board.id, user_id=user.id, role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def change_member_role(db: Session, member: BoardMember, role: BoardRole) -> BoardMember:
    if member.role == BoardRole.OWNER and role != BoardRole.OWNER and _owner_count(db, member.board_id) == 1:
        raise LastOwnerError("A board needs at least one owner")
    member.role = role
    db.commit()
    db.refresh(member)
    return member


def remove_member(db: Session, member: BoardMember) -> None:
    if member.role == BoardRole.OWNER and _owner_count(db, member.board_id) == 1:
        raise LastOwnerError("A board needs at least one owner")
    db.delete(member)
    db.commit()


# ── Lists ──


def _ordered_lists(db: Session, board_id: int, exclude_id: int | None = None) -> list[BoardList]:
    # Archived lists are included: they keep their slot and reappear there when restored.
    stmt = select(BoardList).where(BoardList.board_id == board_id).order_by(BoardList.position, BoardList.id)
    if exclude_id is not None:
        stmt = stmt.where(BoardList.id != exclude_id)
    return list(db.scalars(stmt))


def _place(siblings: list[BoardList], index: int) -> float:
    """A position at `index` among `siblings`, renumbering them first if there's no room."""
    position = ordering.position_at([s.position for s in siblings], index)
    if position is None:
        for sibling, new_position in zip(siblings, ordering.spread(len(siblings))):
            sibling.position = new_position
        position = ordering.position_at([s.position for s in siblings], index)
        assert position is not None  # A freshly spread list always has room.
    return position


def create_list(db: Session, board: Board, name: str) -> BoardList:
    """New lists go at the end of the board."""
    siblings = _ordered_lists(db, board.id)
    board_list = BoardList(board_id=board.id, name=name.strip(), position=_place(siblings, len(siblings)))
    db.add(board_list)
    db.commit()
    db.refresh(board_list)
    return board_list


def move_list(db: Session, board_list: BoardList, after_id: int | None) -> BoardList:
    """Put `board_list` right after list `after_id` (None = first)."""
    if after_id == board_list.id:
        raise InvalidMoveError("A list can't be placed after itself")
    siblings = _ordered_lists(db, board_list.board_id, exclude_id=board_list.id)
    if after_id is None:
        index = 0
    else:
        ids = [s.id for s in siblings]
        if after_id not in ids:
            # Also covers a list on another board: you can't reference what isn't here.
            raise InvalidMoveError("after_id is not a list on this board")
        index = ids.index(after_id) + 1
    board_list.position = _place(siblings, index)
    db.commit()
    db.refresh(board_list)
    return board_list
