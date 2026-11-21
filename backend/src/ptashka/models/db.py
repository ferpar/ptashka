"""SQLAlchemy database models.

Groups:

- **Accounts**: User, RefreshToken.
- **Boards**: Board, BoardMember (who can see/edit a board), BoardList (a column), Card.
- **Card details**: Label + CardLabel, CardAssignee, ChecklistItem, Comment.
"""

from datetime import datetime, timezone
from enum import Enum as PyEnum

from typing import Any

from sqlalchemy import (
    DateTime,
    Dialect,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """A timezone-aware datetime that behaves the same on every database.

    Postgres' `timestamptz` converts offsets correctly, but SQLite has no timezone
    support and silently drops the offset (10:00+01:00 would come back as 10:00).
    So: refuse naive datetimes, convert to UTC before storing, and mark values read
    back as UTC. Code always sees aware UTC datetimes.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime: always use timezone-aware datetimes")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all models. `Base.metadata` knows every table."""


def _enum(cls: type[PyEnum]) -> Enum:
    """Store enums by value (lowercase strings), not by member name, and as a plain
    VARCHAR rather than a native Postgres ENUM, so adding a member needs no migration."""
    return Enum(cls, values_callable=lambda e: [m.value for m in e], native_enum=False, length=20)


# ── Accounts ──


class UserRole(str, PyEnum):
    """Site-wide role. Board permissions are separate (BoardMember.role, phase 2)."""

    USER = "user"
    ADMIN = "admin"


class UserStatus(str, PyEnum):
    """Open sign-up creates PENDING accounts; an admin activates them."""

    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(_enum(UserRole), default=UserRole.USER)
    status: Mapped[UserStatus] = mapped_column(_enum(UserStatus), default=UserStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # SHA-256 of the token: a database leak must not yield usable refresh tokens.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


# ── Boards ──


class BoardRole(str, PyEnum):
    """What a member may do on one board. Ordered: each role includes the ones before it."""

    VIEWER = "viewer"  # read everything (strictly read-only)
    # + work on cards without managing them: move cards, complete/reopen, tick checklist items,
    # comment, assign/unassign *themselves*. Meant for people (or agents) doing the tasks.
    CONTRIBUTOR = "contributor"
    EDITOR = "editor"  # + create/edit/archive cards, lists, labels, checklists; assign anyone
    OWNER = "owner"  # + rename/archive/delete the board, manage members

    @property
    def rank(self) -> int:
        return list(BoardRole).index(self)

    def includes(self, other: "BoardRole") -> bool:
        return self.rank >= other.rank


class Board(Base):
    __tablename__ = "boards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    # Who created it, for the record. Ownership itself lives in BoardMember.
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    # Archived boards are hidden from the board list but keep all their data.
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    # passive_deletes=True on these relationships: when a parent is deleted, let the database's
    # ON DELETE CASCADE remove the children in one statement, instead of SQLAlchemy loading every
    # child (and grandchild...) just to delete them one by one.
    members: Mapped[list["BoardMember"]] = relationship(
        back_populates="board", cascade="all, delete-orphan", passive_deletes=True
    )
    lists: Mapped[list["BoardList"]] = relationship(
        back_populates="board", cascade="all, delete-orphan", passive_deletes=True, order_by="BoardList.position"
    )
    labels: Mapped[list["Label"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="Label.name"
    )


class BoardMember(Base):
    """A user's access to a board. No row = the board doesn't exist, as far as they know."""

    __tablename__ = "board_members"

    # Composite primary key: a user is a member of a board at most once.
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[BoardRole] = mapped_column(_enum(BoardRole))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    board: Mapped[Board] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class BoardList(Base):
    """A column on a board ("To do", "Doing", ...). Named BoardList so it doesn't shadow Python's `list`."""

    __tablename__ = "lists"
    __table_args__ = (
        # (id, board_id) is trivially unique since id alone is, but a foreign key can only point at
        # columns with a unique constraint: this is what cards' composite foreign key references.
        UniqueConstraint("id", "board_id", name="uq_lists_id_board"),
        # A *partial* unique index: uniqueness only among rows where is_done is true,
        # so each board has at most one done list (and any number of ordinary ones).
        Index(
            "uq_lists_one_done_per_board",
            "board_id",
            unique=True,
            postgresql_where=text("is_done"),
            sqlite_where=text("is_done"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # Sort key, see services/ordering.py. Gaps are intentional.
    position: Mapped[float] = mapped_column(Float)
    # Moving a card into the done list completes it; moving it out reopens it.
    # server_default fills existing rows when the migration adds the column.
    is_done: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    board: Mapped[Board] = relationship(back_populates="lists")
    cards: Mapped[list["Card"]] = relationship(
        # A lambda, because Card isn't defined yet when this line runs. Ties (possible if two
        # moves race) are broken by id, so the order is always deterministic.
        back_populates="board_list",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: [Card.position, Card.id],
    )


class Card(Base):
    """A task. Lives in one list; moves between lists of the same board."""

    __tablename__ = "cards"
    __table_args__ = (
        # The board view reads "cards of list X in order": one index serves both the filter and the sort.
        Index("ix_cards_list_position", "list_id", "position"),
        # Referenced by card_labels / card_assignees, like uq_lists_id_board is by cards.
        UniqueConstraint("id", "board_id", name="uq_cards_id_board"),
        # The database guarantees the denormalized board_id matches the list's board: a card
        # pointing at (list 3, board 2) is rejected unless list 3 really is on board 2.
        # ON UPDATE CASCADE: if a list ever moves to another board, its cards' board_id follows.
        ForeignKeyConstraint(
            ["list_id", "board_id"],
            ["lists.id", "lists.board_id"],
            name="fk_cards_list_board",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int]
    # Denormalized: derivable via list_id → lists.board_id, but stored so permission checks and
    # cross-board queries ("my cards everywhere", phase 5) don't need a join. Kept honest by
    # fk_cards_list_board above.
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), index=True)

    # Optimistic locking: SQLAlchemy sets version=1 on INSERT, bumps it on every UPDATE and adds
    # `WHERE version = <the value it loaded>`. If another transaction got there first, no row
    # matches and the flush raises StaleDataError instead of silently overwriting.
    version: Mapped[int] = mapped_column(server_default="1")
    __mapper_args__ = {"version_id_col": version}
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)  # Markdown.
    position: Mapped[float] = mapped_column(Float)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    # onupdate runs whenever SQLAlchemy issues an UPDATE for this row.
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    board_list: Mapped[BoardList] = relationship(back_populates="cards")
    label_links: Mapped[list["CardLabel"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    assignee_links: Mapped[list["CardAssignee"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    checklist_items: Mapped[list["ChecklistItem"]] = relationship(
        back_populates="card",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: [ChecklistItem.position, ChecklistItem.id],
    )

    # Plain Python properties: Pydantic's from_attributes reads these like columns.
    @property
    def label_ids(self) -> list[int]:
        return sorted(link.label_id for link in self.label_links)

    @property
    def assignee_ids(self) -> list[int]:
        return sorted(link.user_id for link in self.assignee_links)


# ── Card details ──


class LabelColor(str, PyEnum):
    """A fixed palette: the frontend maps each name to colours that work in light and dark themes."""

    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"
    PURPLE = "purple"
    BLUE = "blue"
    SKY = "sky"
    LIME = "lime"
    PINK = "pink"
    GRAY = "gray"


class Label(Base):
    """A board's tag ("bug", "urgent"...). Cards can only use labels from their own board."""

    __tablename__ = "labels"
    __table_args__ = (
        UniqueConstraint("board_id", "name", name="uq_labels_board_name"),
        UniqueConstraint("id", "board_id", name="uq_labels_id_board"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(50))
    color: Mapped[LabelColor] = mapped_column(_enum(LabelColor))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class CardLabel(Base):
    """Links a card to a label. board_id appears in *both* composite foreign keys, so the database
    guarantees the card and the label are on the same board."""

    __tablename__ = "card_labels"
    __table_args__ = (
        ForeignKeyConstraint(
            ["card_id", "board_id"], ["cards.id", "cards.board_id"], ondelete="CASCADE", onupdate="CASCADE"
        ),
        ForeignKeyConstraint(["label_id", "board_id"], ["labels.id", "labels.board_id"], ondelete="CASCADE"),
    )

    card_id: Mapped[int] = mapped_column(primary_key=True)
    label_id: Mapped[int] = mapped_column(primary_key=True, index=True)
    board_id: Mapped[int]


class CardAssignee(Base):
    """Links a card to a user responsible for it. The (board_id, user_id) foreign key points at
    board_members, so only members can be assigned, and leaving a board (deleting the membership)
    removes that person's assignments on it automatically."""

    __tablename__ = "card_assignees"
    __table_args__ = (
        ForeignKeyConstraint(
            ["card_id", "board_id"], ["cards.id", "cards.board_id"], ondelete="CASCADE", onupdate="CASCADE"
        ),
        ForeignKeyConstraint(
            ["board_id", "user_id"], ["board_members.board_id", "board_members.user_id"], ondelete="CASCADE"
        ),
        # Phase 5's "cards assigned to me, across boards" starts from the user.
        Index("ix_card_assignees_user", "user_id"),
    )

    card_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int]


class ChecklistItem(Base):
    """A sub-task of a card, ordered like cards are (see services/ordering.py)."""

    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    position: Mapped[float] = mapped_column(Float)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    card: Mapped[Card] = relationship(back_populates="checklist_items")


class Comment(Base):
    __tablename__ = "comments"
    # The card view lists a card's comments oldest first.
    __table_args__ = (Index("ix_comments_card_created", "card_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"))
    # SET NULL: if the author's account is deleted, the conversation keeps its shape.
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)  # Markdown.
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    author: Mapped[User | None] = relationship()
