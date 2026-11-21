"""Board endpoints: boards, members, and creating lists on a board."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ptashka.auth.board_access import BoardAccess, board_access
from ptashka.auth.dependencies import get_current_user
from ptashka.db.database import get_db
from ptashka.models.db import Board, BoardList, BoardMember, BoardRole, Card, User
from ptashka.models.schemas import (
    BoardCreateRequest,
    BoardDetail,
    BoardListResponse,
    BoardSummary,
    BoardUpdateRequest,
    LabelCreateRequest,
    LabelListResponse,
    LabelSchema,
    ListCreateRequest,
    ListSchema,
    ListWithCards,
    MemberAddRequest,
    MemberListResponse,
    MemberSchema,
    MemberUpdateRequest,
)
from ptashka.api.presenters import card_schema
from ptashka.services import board_service, card_service, label_service

router = APIRouter(prefix="/api/boards", tags=["boards"])


def _summary(board: Board, role: BoardRole) -> BoardSummary:
    return BoardSummary(
        id=board.id,
        name=board.name,
        description=board.description,
        my_role=role,
        created_at=board.created_at,
        archived_at=board.archived_at,
    )


def _detail(db: Session, access: BoardAccess, include_archived: bool) -> BoardDetail:
    board = board_service.load_board_tree(db, access.board.id)
    stats = card_service.stats_for_board(db, board.id)

    def visible(item: BoardList | Card) -> bool:
        return include_archived or item.archived_at is None

    lists = [
        ListWithCards(
            **ListSchema.model_validate(lst).model_dump(),
            cards=[card_schema(c, stats[c.id]) for c in lst.cards if visible(c)],
        )
        for lst in board.lists
        if visible(lst)
    ]
    members = sorted(board.members, key=lambda m: m.added_at)
    return BoardDetail(
        **_summary(board, access.role).model_dump(),
        lists=lists,
        members=[MemberSchema.model_validate(m) for m in members],
        labels=[LabelSchema.model_validate(label) for label in board.labels],
    )


# ── Boards ──


@router.get("", response_model=BoardListResponse)
def list_boards(
    include_archived: bool = False,  # A plain typed parameter becomes a query param: ?include_archived=true
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BoardListResponse:
    """The boards you're a member of."""
    rows = board_service.boards_for_user(db, user, include_archived)
    return BoardListResponse(boards=[_summary(board, role) for board, role in rows])


@router.post("", response_model=BoardDetail, status_code=status.HTTP_201_CREATED)
def create_board(
    request: BoardCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> BoardDetail:
    """Create a board. You become its owner."""
    board = board_service.create_board(db, user, request.name, request.description, request.default_lists)
    return _detail(db, BoardAccess(board=board, role=BoardRole.OWNER, user=user), include_archived=False)


@router.get("/{board_id}", response_model=BoardDetail)
def get_board(
    include_archived: bool = False,
    access: BoardAccess = Depends(board_access(BoardRole.VIEWER)),
    db: Session = Depends(get_db),
) -> BoardDetail:
    """The board with its lists, cards and members. Archived lists and cards are left out unless asked for."""
    return _detail(db, access, include_archived)


@router.patch("/{board_id}", response_model=BoardDetail)
def update_board(
    request: BoardUpdateRequest,
    access: BoardAccess = Depends(board_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> BoardDetail:
    """Rename or describe the board (editors). Archiving/restoring (`archived`) needs an owner."""
    changes = request.model_dump(exclude_unset=True)
    if "archived" in changes:
        if not access.role.includes(BoardRole.OWNER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires owner access")
        if changes["archived"] is not None:
            board_service.set_archived(access.board, changes["archived"])
    if changes.get("name") is not None:
        access.board.name = changes["name"].strip()
    if "description" in changes:  # null is allowed here: it clears the description.
        access.board.description = changes["description"]
    db.commit()
    return _detail(db, access, include_archived=False)


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_board(
    access: BoardAccess = Depends(board_access(BoardRole.OWNER)), db: Session = Depends(get_db)
) -> Response:
    """Delete the board and everything on it, permanently. Prefer archiving."""
    db.delete(access.board)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Members ──


def _get_member(db: Session, board_id: int, user_id: int) -> BoardMember:
    member = db.get(BoardMember, (board_id, user_id))
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return member


@router.get("/{board_id}/members", response_model=MemberListResponse)
def list_members(access: BoardAccess = Depends(board_access(BoardRole.VIEWER))) -> MemberListResponse:
    members = sorted(access.board.members, key=lambda m: m.added_at)
    return MemberListResponse(members=[MemberSchema.model_validate(m) for m in members])


@router.post("/{board_id}/members", response_model=MemberSchema, status_code=status.HTTP_201_CREATED)
def add_member(
    request: MemberAddRequest,
    access: BoardAccess = Depends(board_access(BoardRole.OWNER)),
    db: Session = Depends(get_db),
) -> BoardMember:
    """Share the board with an active user, by email."""
    try:
        return board_service.add_member(db, access.board, request.email, request.role)
    except board_service.UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except board_service.AlreadyMemberError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/{board_id}/members/{user_id}", response_model=MemberSchema)
def update_member(
    user_id: int,
    request: MemberUpdateRequest,
    access: BoardAccess = Depends(board_access(BoardRole.OWNER)),
    db: Session = Depends(get_db),
) -> BoardMember:
    member = _get_member(db, access.board.id, user_id)
    try:
        return board_service.change_member_role(db, member, request.role)
    except board_service.LastOwnerError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.delete("/{board_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: int,
    access: BoardAccess = Depends(board_access(BoardRole.VIEWER)),
    db: Session = Depends(get_db),
) -> Response:
    """Owners can remove anyone; any member can remove themselves (leave the board)."""
    if user_id != access.user.id and not access.role.includes(BoardRole.OWNER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires owner access")
    member = _get_member(db, access.board.id, user_id)
    try:
        board_service.remove_member(db, member)
    except board_service.LastOwnerError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Lists on a board ──


@router.post("/{board_id}/lists", response_model=ListSchema, status_code=status.HTTP_201_CREATED)
def create_list(
    request: ListCreateRequest,
    access: BoardAccess = Depends(board_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> ListSchema:
    """Add a list at the end of the board."""
    return ListSchema.model_validate(board_service.create_list(db, access.board, request.name))


# ── Labels on a board ──


@router.get("/{board_id}/labels", response_model=LabelListResponse)
def list_labels(
    access: BoardAccess = Depends(board_access(BoardRole.VIEWER)), db: Session = Depends(get_db)
) -> LabelListResponse:
    labels = label_service.labels_for_board(db, access.board.id)
    return LabelListResponse(labels=[LabelSchema.model_validate(label) for label in labels])


@router.post("/{board_id}/labels", response_model=LabelSchema, status_code=status.HTTP_201_CREATED)
def create_label(
    request: LabelCreateRequest,
    access: BoardAccess = Depends(board_access(BoardRole.EDITOR)),
    db: Session = Depends(get_db),
) -> LabelSchema:
    try:
        label = label_service.create_label(db, access.board, request.name, request.color)
    except label_service.LabelExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return LabelSchema.model_validate(label)
