"""Card endpoints addressed by card id (creating a card lives under /api/lists/{id}/cards)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import AwareDatetime

from ptashka.api.activity import Limit, page
from ptashka.api.presenters import card_detail, search_hits
from ptashka.auth.board_access import CardAccess, card_access, check_fields
from ptashka.auth.dependencies import get_current_user
from ptashka.db.database import DbSession
from ptashka.models.db import BoardRole, User
from ptashka.models.schemas import (
    ActivityPage,
    CardDetail,
    CardMoveRequest,
    CardSearchResponse,
    CardUpdateRequest,
    ChecklistItemCreateRequest,
    ChecklistItemSchema,
    CommentListResponse,
    CommentRequest,
    CommentSchema,
)
from ptashka.services import activity_service, card_service, checklist_service, comment_service, label_service, search_service
from ptashka.services.search_service import CardFilters
from ptashka.services.board_service import InvalidMoveError

router = APIRouter(prefix="/api/cards", tags=["cards"])

NO_CONTENT = Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=CardSearchResponse)
def search(
    db: DbSession,
    assignee: str | None = Query(default=None, description='"me", or a user id'),
    board_id: int | None = None,
    label: str | None = Query(default=None, max_length=50, description="A label name (case-insensitive), on any board"),
    due_before: AwareDatetime | None = None,
    due_after: AwareDatetime | None = None,
    overdue: bool = False,
    completed: bool | None = None,
    archived: bool = Query(default=False, description="Include archived cards, lists and boards"),
    q: str | None = Query(default=None, max_length=200, description="Text in title or description"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
) -> CardSearchResponse:
    """Search cards across every board you're a member of. Soonest due first, undated last.

    e.g. your open tasks: `?assignee=me&completed=false`; this week's: add `&due_before=...`.
    """
    if assignee is None or assignee == "me":
        assignee_id = user.id if assignee == "me" else None
    elif assignee.isdigit():
        assignee_id = int(assignee)
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail='assignee must be "me" or a user id')
    filters = CardFilters(
        assignee_id=assignee_id,
        board_id=board_id,
        label=label,
        due_before=due_before,
        due_after=due_after,
        overdue=overdue,
        completed=completed,
        include_archived=archived,
        text=q,
    )
    hits = search_service.search_cards(db, user.id, filters, limit + 1, offset)  # One extra: is there more?
    return CardSearchResponse(
        cards=search_hits(db, hits[:limit]),
        next_offset=offset + limit if len(hits) > limit else None,
    )


@router.get("/{card_id}", response_model=CardDetail)
def get_card(db: DbSession, access: CardAccess = Depends(card_access(BoardRole.VIEWER))) -> CardDetail:
    return card_detail(db, access.card)


@router.patch("/{card_id}", response_model=CardDetail)
def update_card(
    db: DbSession,
    request: CardUpdateRequest,
    access: CardAccess = Depends(card_access(BoardRole.CONTRIBUTOR)),
) -> CardDetail:
    """Edit fields. `completed` / `archived` take booleans; `description` / `due_at` can be cleared with null.

    Contributors may only send `completed` (and `version`); every other field requires editor.
    Send the `version` you loaded to get a 409 instead of overwriting a change made since.
    """
    changes = request.model_dump(exclude_unset=True)
    check_fields(access.access.role, changes, allowed={"completed", "version"}, above=BoardRole.EDITOR)
    try:
        card = card_service.update_card(db, access.access.user, access.card, changes)
    except card_service.VersionConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(e), "current_version": e.current_version},
        )
    return card_detail(db, card)


@router.post("/{card_id}/move", response_model=CardDetail)
def move_card(
    db: DbSession,
    request: CardMoveRequest,
    access: CardAccess = Depends(card_access(BoardRole.CONTRIBUTOR)),
) -> CardDetail:
    """Move within a list or to another list on the same board (contributors and up)."""
    try:
        card = card_service.move_card(db, access.access.user, access.card, request.list_id, request.after_id)
    except InvalidMoveError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    return card_detail(db, card)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(
    db: DbSession,
    access: CardAccess = Depends(card_access(BoardRole.EDITOR))
) -> Response:
    """Delete permanently. Prefer archiving (`PATCH {"archived": true}`)."""
    card_service.delete_card(db, access.access.user, access.card)
    return NO_CONTENT


# ── Labels and assignees ──
# PUT adds, DELETE removes; both are idempotent, so a client (or agent) can retry them safely:
# PUT on a label the card already has, or DELETE on one it doesn't, just succeeds.


@router.put("/{card_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_label(
    db: DbSession,
    label_id: int, access: CardAccess = Depends(card_access(BoardRole.EDITOR))
) -> Response:
    try:
        label_service.attach(db, access.access.user, access.card, label_id)
    except label_service.LabelNotOnBoardError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    return NO_CONTENT


@router.delete("/{card_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_label(
    db: DbSession,
    label_id: int, access: CardAccess = Depends(card_access(BoardRole.EDITOR))
) -> Response:
    label_service.detach(db, access.access.user, access.card, label_id)
    return NO_CONTENT


def _check_self_or_editor(access: CardAccess, user_id: int) -> None:
    """Contributors can take a card themselves ("I'll do it"); handing out work is for editors."""
    if user_id != access.access.user.id and not access.access.role.includes(BoardRole.EDITOR):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contributors can only assign themselves")


@router.put("/{card_id}/assignees/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def assign(
    db: DbSession,
    user_id: int, access: CardAccess = Depends(card_access(BoardRole.CONTRIBUTOR))
) -> Response:
    """Assign a board member (any role) to the card. Contributors may only assign themselves."""
    _check_self_or_editor(access, user_id)
    try:
        card_service.assign(db, access.access.user, access.card, user_id)
    except card_service.NotAMemberError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    return NO_CONTENT


@router.delete("/{card_id}/assignees/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign(
    db: DbSession,
    user_id: int, access: CardAccess = Depends(card_access(BoardRole.CONTRIBUTOR))
) -> Response:
    """Contributors may only unassign themselves."""
    _check_self_or_editor(access, user_id)
    card_service.unassign(db, access.access.user, access.card, user_id)
    return NO_CONTENT


# ── Checklist and comments on a card ──


@router.post("/{card_id}/checklist", response_model=ChecklistItemSchema, status_code=status.HTTP_201_CREATED)
def add_checklist_item(
    db: DbSession,
    request: ChecklistItemCreateRequest,
    access: CardAccess = Depends(card_access(BoardRole.EDITOR)),
) -> ChecklistItemSchema:
    """Add an item at the end of the card's checklist."""
    return ChecklistItemSchema.model_validate(checklist_service.add_item(db, access.access.user, access.card, request.text))


@router.get("/{card_id}/comments", response_model=CommentListResponse)
def list_comments(
    db: DbSession,
    access: CardAccess = Depends(card_access(BoardRole.VIEWER))
) -> CommentListResponse:
    """Oldest first."""
    comments = comment_service.list_comments(db, access.card)
    return CommentListResponse(comments=[CommentSchema.model_validate(c) for c in comments])


@router.post("/{card_id}/comments", response_model=CommentSchema, status_code=status.HTTP_201_CREATED)
def add_comment(
    db: DbSession,
    request: CommentRequest,
    access: CardAccess = Depends(card_access(BoardRole.CONTRIBUTOR)),
) -> CommentSchema:
    comment = comment_service.add_comment(db, access.access.user, access.card, request.body)
    return CommentSchema.model_validate(comment)


@router.get("/{card_id}/activity", response_model=ActivityPage)
def card_activity(
    db: DbSession,
    before: int | None = Query(default=None, ge=1),
    limit: int = Limit,
    access: CardAccess = Depends(card_access(BoardRole.VIEWER)),
) -> ActivityPage:
    """This card's history, newest first."""
    return page(lambda n: activity_service.card_page(db, access.card.id, n, before), limit)
