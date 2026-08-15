"""The tools the agent may call, and the dispatcher that runs one.

Every tool goes through the same `app.services` functions the HTTP routers use.
There is deliberately no second, less-guarded path to the database for the agent:
the ownership filters phase 2 proved load-bearing are the same objects here, so
they cannot rot on one path while staying correct on the other.

Two scoping properties, both structural rather than instructional:

1. **The user is not a parameter.** A tool receives the authenticated `User` from
   the request context. There is no user id in any argument schema below, so
   there is nothing for a model to be argued into changing. Whatever a card's
   text says, the query still filters on the caller.

2. **The board is not a parameter either.** The chat is bound to one board taken
   from the URL and ownership-checked once, before the model is ever called. A
   column or card id that resolves outside that board is refused with the same
   404 the rest of the application gives, so the agent cannot be walked onto the
   caller's *other* boards, let alone anyone else's.

The second is a narrowing of the first, not a replacement for it. Removing it
would still leave tenant isolation intact; it exists so the blast radius of a
successful injection is one board rather than an account.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BoardColumn, Card, User
from app.services import boards, cards
from app.services.cards import get_owned_card
from app.services.columns import get_owned_column


@dataclass(frozen=True)
class ToolContext:
    """Who the tool acts as, and where.

    Both fields are set by the endpoint from the session cookie and the URL. A
    tool cannot widen either one.
    """

    session: AsyncSession
    user: User
    board_id: uuid.UUID


class ToolArgs(BaseModel):
    """Base for every tool's arguments.

    extra="forbid" for the same reason `StrictModel` does it on request bodies:
    an argument the tool does not define is a malformed call and is answered as
    one, rather than being dropped so that a call which did something other than
    what it said looks like it succeeded.
    """

    model_config = ConfigDict(extra="forbid")


Title = Field(min_length=1, max_length=200)


class ListBoardArgs(ToolArgs):
    pass


class CreateCardArgs(ToolArgs):
    column_id: uuid.UUID
    title: str = Title
    description: str | None = None


class EditCardArgs(ToolArgs):
    card_id: uuid.UUID
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class MoveCardArgs(ToolArgs):
    card_id: uuid.UUID
    column_id: uuid.UUID
    position: int = Field(ge=0)


class DeleteCardArgs(ToolArgs):
    card_id: uuid.UUID


async def _column_on_board(ctx: ToolContext, column_id: uuid.UUID) -> BoardColumn:
    """A column the caller owns, on the bound board, or 404."""
    column = await get_owned_column(ctx.session, ctx.user, column_id)
    if column.board_id != ctx.board_id:
        # The same wording get_owned_column gives for a column belonging to
        # somebody else. A different message here would say "this exists, it is
        # yours, but not on this board", which is a distinction the caller can
        # already discover legitimately and the agent has no reason to surface.
        raise HTTPException(404, detail="Column not found")
    return column


async def _card_on_board(ctx: ToolContext, card_id: uuid.UUID) -> Card:
    """A card the caller owns, on the bound board, or 404.

    The board check is made here rather than by delegating to _column_on_board,
    which would answer "Column not found" to a question about a card. That is
    both the wrong noun and a hint about which layer refused.
    """
    card = await get_owned_card(ctx.session, ctx.user, card_id)
    column = await get_owned_column(ctx.session, ctx.user, card.column_id)
    if column.board_id != ctx.board_id:
        raise HTTPException(404, detail="Card not found")
    return card


async def list_board(ctx: ToolContext, args: ListBoardArgs) -> dict[str, Any]:
    board = await boards.get_owned_board(
        ctx.session, ctx.user, ctx.board_id, with_contents=True
    )
    return {
        "board_title": board.title,
        "columns": [
            {
                "column_id": str(column.id),
                "title": column.title,
                "position": column.position,
                "cards": [
                    {
                        "card_id": str(card.id),
                        "title": card.title,
                        "description": card.description,
                        "position": card.position,
                    }
                    for card in column.cards
                ],
            }
            for column in board.columns
        ],
    }


async def create_card(ctx: ToolContext, args: CreateCardArgs) -> dict[str, Any]:
    column = await _column_on_board(ctx, args.column_id)
    card = await cards.create_card(
        ctx.session, ctx.user, column.id, args.title, args.description
    )
    return _card_result(card)


async def edit_card(ctx: ToolContext, args: EditCardArgs) -> dict[str, Any]:
    card = await _card_on_board(ctx, args.card_id)
    updated = await cards.update_card(
        ctx.session,
        ctx.user,
        card.id,
        args.title,
        args.description,
        # Same "provided" distinction the PATCH route makes: description is
        # nullable, so clearing it and leaving it alone are different requests.
        description_provided="description" in args.model_fields_set,
    )
    return _card_result(updated)


async def move_card(ctx: ToolContext, args: MoveCardArgs) -> dict[str, Any]:
    card = await _card_on_board(ctx, args.card_id)
    await _column_on_board(ctx, args.column_id)
    moved = await cards.move_card(
        ctx.session, ctx.user, card.id, args.column_id, args.position
    )
    return _card_result(moved)


async def delete_card(ctx: ToolContext, args: DeleteCardArgs) -> dict[str, Any]:
    card = await _card_on_board(ctx, args.card_id)
    title = card.title
    await cards.delete_card(ctx.session, ctx.user, card.id)
    return {"deleted": True, "card_id": str(args.card_id), "title": title}


def _card_result(card: Card) -> dict[str, Any]:
    return {
        "card_id": str(card.id),
        "column_id": str(card.column_id),
        "title": card.title,
        "description": card.description,
        "position": card.position,
    }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[ToolArgs]
    handler: Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]
    # Whether a successful call changes the database. The mutation budget in the
    # injection defence counts these, so it is a property of the tool rather than
    # something the caller has to remember.
    mutates: bool


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            name="list_board",
            description=(
                "List the board's columns and the cards in each, with their ids. "
                "Call this first when you need an id, because ids are not "
                "guessable and must never be invented."
            ),
            args_model=ListBoardArgs,
            handler=list_board,
            mutates=False,
        ),
        ToolSpec(
            name="create_card",
            description="Create a card at the end of a column on this board.",
            args_model=CreateCardArgs,
            handler=create_card,
            mutates=True,
        ),
        ToolSpec(
            name="edit_card",
            description=(
                "Change a card's title, its description, or both. Omit a field to "
                "leave it as it is."
            ),
            args_model=EditCardArgs,
            handler=edit_card,
            mutates=True,
        ),
        ToolSpec(
            name="move_card",
            description=(
                "Move a card to a column on this board and to a position within "
                "it. Position 0 is the top."
            ),
            args_model=MoveCardArgs,
            handler=move_card,
            mutates=True,
        ),
        ToolSpec(
            name="delete_card",
            description="Delete a card from this board. This cannot be undone.",
            args_model=DeleteCardArgs,
            handler=delete_card,
            mutates=True,
        ),
    )
}


@dataclass(frozen=True)
class ToolResult:
    """What running one tool produced.

    An error is a value rather than an exception because a tool failing is an
    ordinary event in a conversation: the model asked for a card that is not
    there, and the useful response is to tell it so and let it try again. Only
    the wording below reaches the model, and each string is either fixed here or
    comes from a service that already answers uniformly.
    """

    name: str
    ok: bool
    content: dict[str, Any]
    mutated: bool


def tool_definitions() -> list[dict[str, Any]]:
    """The tool list in the shape the OpenAI-compatible API expects.

    Generated from the same Pydantic models the dispatcher validates against, so
    the schema advertised to the model and the schema enforced on its reply
    cannot drift apart.
    """
    definitions = []
    for spec in TOOLS.values():
        schema = spec.args_model.model_json_schema()
        schema.pop("title", None)
        definitions.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": schema,
                },
            }
        )
    return definitions


async def dispatch(
    ctx: ToolContext, name: str, arguments: dict[str, Any]
) -> ToolResult:
    """Validate and run one tool call.

    Nothing about `name` or `arguments` is trusted: they are whatever the model
    emitted, which is downstream of text an attacker may control.
    """
    spec = TOOLS.get(name)
    if spec is None:
        return ToolResult(
            name=name,
            ok=False,
            content={"error": f"There is no tool called {name!r}."},
            mutated=False,
        )

    try:
        args = spec.args_model.model_validate(arguments)
    except ValidationError as exc:
        return ToolResult(
            name=name,
            ok=False,
            content={
                "error": "Those arguments are not valid for this tool.",
                "details": [
                    {"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]}
                    for e in exc.errors()
                ],
            },
            mutated=False,
        )

    try:
        content = await spec.handler(ctx, args)
    except HTTPException as exc:
        # Ownership refusals land here. The detail is already the uniform wording
        # the rest of the application uses, so relaying it tells the model that
        # the card is unreachable without telling it whether it exists.
        return ToolResult(
            name=name, ok=False, content={"error": exc.detail}, mutated=False
        )

    return ToolResult(name=name, ok=True, content=content, mutated=spec.mutates)
