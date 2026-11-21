"""Turning models into response schemas when a plain `model_validate` isn't enough.

Cards combine row fields with counts computed by aggregate queries, and several routers
(boards, lists, cards) return them, so the assembly lives here once.
"""

from dataclasses import asdict

from sqlalchemy.orm import Session

from ptashka.models.db import Card
from ptashka.models.schemas import CardBase, CardDetail, CardSchema, ChecklistItemSchema
from ptashka.services import card_service
from ptashka.services.card_service import CardStats


def card_schema(card: Card, stats: CardStats) -> CardSchema:
    return CardSchema(**CardBase.model_validate(card).model_dump(), **asdict(stats))


def card_detail(db: Session, card: Card) -> CardDetail:
    """A single card with its checklist. A few small queries: fine for one card, never use in a loop."""
    db.refresh(card)  # Links/items may have changed in this request; reload them.
    return CardDetail(
        **card_schema(card, card_service.stats_for_card(db, card.id)).model_dump(),
        checklist=[ChecklistItemSchema.model_validate(item) for item in card.checklist_items],
    )
