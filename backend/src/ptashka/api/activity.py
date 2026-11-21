"""Activity endpoints. Per-board and per-card history live under their routers and use `page()`."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, Query

from ptashka.auth.dependencies import get_current_user
from ptashka.db.database import DbSession
from ptashka.models.db import Activity, User
from ptashka.models.schemas import ActivityFeed, ActivityPage, ActivitySchema
from ptashka.services import activity_service

router = APIRouter(prefix="/api/activity", tags=["activity"])

Limit = Query(default=50, ge=1, le=200)


def page(fetch: Callable[[int], list[Activity]], limit: int) -> ActivityPage:
    """Fetch one row more than asked for: if it exists, there's another page. Cheaper than a COUNT(*)."""
    rows = fetch(limit + 1)
    has_more = len(rows) > limit
    rows = rows[:limit]
    return ActivityPage(
        activities=[ActivitySchema.model_validate(a) for a in rows],
        next_before=rows[-1].id if has_more else None,
    )


@router.get("", response_model=ActivityFeed)
def feed(
    db: DbSession,
    since: int = Query(default=0, ge=0),
    limit: int = Limit,
    user: User = Depends(get_current_user),
) -> ActivityFeed:
    """What changed on any of your boards after entry `since`, oldest first.

    Built for polling (e.g. an agent checking in every few minutes): keep `next_since` and send it
    back next time. Entries appear a few seconds after they happen, so that one committed late is
    never skipped.
    """
    rows = activity_service.feed(db, user, since, limit)
    return ActivityFeed(
        activities=[ActivitySchema.model_validate(a) for a in rows],
        next_since=rows[-1].id if rows else since,
    )
