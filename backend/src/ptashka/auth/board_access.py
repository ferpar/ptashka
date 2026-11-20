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

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ptashka.auth.dependencies import get_current_user
from ptashka.db.database import get_db
from ptashka.models.db import Board, BoardList, BoardMember, BoardRole, User


@dataclass
class BoardAccess:
    board: Board
    role: BoardRole
    user: User


@dataclass
class ListAccess:
    board_list: BoardList
    access: BoardAccess


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
        board_id: int,  # FastAPI fills this from the path, just like in an endpoint.
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> BoardAccess:
        return _check(db, user, board_id, minimum)

    return dependency


def list_access(minimum: BoardRole) -> Callable[..., ListAccess]:
    """Dependency for routes with a `{list_id}` path parameter: find the list, then check its board."""

    def dependency(
        list_id: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> ListAccess:
        board_list = db.get(BoardList, list_id)
        if board_list is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
        try:
            access = _check(db, user, board_list.board_id, minimum)
        except HTTPException as e:
            if e.status_code == status.HTTP_404_NOT_FOUND:
                # Same message as a missing list: don't reveal that it exists on someone else's board.
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
            raise
        return ListAccess(board_list=board_list, access=access)

    return dependency
