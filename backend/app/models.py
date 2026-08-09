import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.uuidv7()
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # Argon2id, from pwdlib. Never the password, never logged. The column is a
    # plain str here and a plain Text in Postgres because the hash carries its own
    # algorithm and parameters, which is what makes verify_and_update able to
    # rehash on a future parameter change.
    password_hash: Mapped[str] = mapped_column(Text)
    # Per-account login backoff. Reset on a successful login.
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserSession(Base):
    """One signed-in session.

    The table is `sessions`; the class is not, because `Session` would read as
    SQLAlchemy's `Session` in every module that handles both, and those two things
    are a request's database handle and a user's login respectively.

    There is no relationship to User on purpose. Nothing needs to walk from a user
    to their sessions in the ORM, and the cascade that matters is the database's
    ON DELETE CASCADE, which holds whether or not the ORM is involved.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.uuidv7()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Board(Base):
    __tablename__ = "boards"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.uuidv7()
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # lazy="raise" on purpose. Under async SQLAlchemy an accidental lazy load
    # fails with MissingGreenlet at some unrelated point later; this turns it into
    # an immediate, obvious error at the access site and forces every caller to
    # say what it wants eagerly loaded.
    columns: Mapped[list["BoardColumn"]] = relationship(
        back_populates="board",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BoardColumn.position",
        lazy="raise",
    )


class BoardColumn(Base):
    """A column on a board.

    The table is `columns`; the class is not, because `Column` would shadow
    SQLAlchemy's own `Column` in any module that imports both.
    """

    __tablename__ = "columns"
    __table_args__ = (
        # Deferrable so a reorder can renumber rows inside one transaction without
        # tripping the constraint on an intermediate state where two rows briefly
        # share a position.
        UniqueConstraint(
            "board_id",
            "position",
            name="uq_columns_board_id_position",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.uuidv7()
    )
    board_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    board: Mapped[Board] = relationship(back_populates="columns", lazy="raise")
    cards: Mapped[list["Card"]] = relationship(
        back_populates="column",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Card.position",
        lazy="raise",
    )


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (
        UniqueConstraint(
            "column_id",
            "position",
            name="uq_cards_column_id_position",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.uuidv7()
    )
    column_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("columns.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    column: Mapped[BoardColumn] = relationship(back_populates="cards", lazy="raise")
