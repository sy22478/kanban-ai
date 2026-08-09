import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


class RegisterRequest(StrictModel):
    email: EmailStr
    # OWASP: a length floor, a generous ceiling, and no composition rules. The
    # ceiling is not cosmetic. Argon2 over an unbounded input is a memory denial
    # of service: a megabyte password would be hashed at 64 MiB just as happily
    # as a short one.
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(StrictModel):
    email: EmailStr
    # Deliberately no minimum, unlike registration. A floor here would answer 422
    # for a short password and 401 for a wrong one, which tells an attacker
    # something about the rules and would lock out anyone whose password predates
    # a future policy change. The ceiling stays, because it is the DoS bound.
    password: str = Field(max_length=128)


class UserRead(ReadModel):
    """What the API says about a user.

    Never the ORM model. `password_hash` is a column on User and reusing that
    class as a response_model is how it ends up in a JSON body; keeping read and
    write schemas apart means it cannot.
    """

    id: uuid.UUID
    email: str
