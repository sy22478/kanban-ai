import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base for every request body.

    extra="forbid" so an unexpected field is a 422 rather than something silently
    dropped. CLAUDE.md asks for malformed input to be rejected, not coerced.
    """

    model_config = ConfigDict(extra="forbid")


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


Title = Field(min_length=1, max_length=200)


class BoardCreate(StrictModel):
    title: str = Title


class BoardUpdate(StrictModel):
    title: str = Title


class ColumnCreate(StrictModel):
    title: str = Title


class ColumnUpdate(StrictModel):
    title: str = Title


class ColumnMove(StrictModel):
    position: int = Field(ge=0)


class CardCreate(StrictModel):
    title: str = Title
    description: str | None = None


class CardUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class CardMove(StrictModel):
    column_id: uuid.UUID
    position: int = Field(ge=0)


class CardRead(ReadModel):
    id: uuid.UUID
    column_id: uuid.UUID
    title: str
    description: str | None
    position: int


class ColumnRead(ReadModel):
    id: uuid.UUID
    board_id: uuid.UUID
    title: str
    position: int


class ColumnWithCards(ColumnRead):
    cards: list[CardRead]


class BoardRead(ReadModel):
    id: uuid.UUID
    title: str
    created_at: datetime


class BoardDetail(BoardRead):
    columns: list[ColumnWithCards]


class UserRead(ReadModel):
    id: uuid.UUID
    email: str
