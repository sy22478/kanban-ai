import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ordering
from app.models import Board, BoardColumn, Card, User
from app.services.columns import get_owned_column


async def list_cards(session: AsyncSession, column_id: uuid.UUID) -> list[Card]:
    result = await session.execute(
        select(Card).where(Card.column_id == column_id).order_by(Card.position)
    )
    return list(result.scalars())


async def get_owned_card(
    session: AsyncSession, user: User, card_id: uuid.UUID
) -> Card:
    """Fetch a card the user owns, or raise 404.

    Joined all the way up through columns to boards. The card id alone carries no
    authority.
    """
    result = await session.execute(
        select(Card)
        .join(BoardColumn, Card.column_id == BoardColumn.id)
        .join(Board, BoardColumn.board_id == Board.id)
        .where(Card.id == card_id, Board.owner_id == user.id)
    )
    card = result.scalar_one_or_none()
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card


async def create_card(
    session: AsyncSession,
    user: User,
    column_id: uuid.UUID,
    title: str,
    description: str | None,
) -> Card:
    column = await get_owned_column(session, user, column_id)
    siblings = await list_cards(session, column.id)

    card = Card(
        column_id=column.id,
        title=title,
        description=description,
        position=len(siblings),
    )
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return card


async def update_card(
    session: AsyncSession,
    user: User,
    card_id: uuid.UUID,
    title: str | None,
    description: str | None,
    description_provided: bool,
) -> Card:
    card = await get_owned_card(session, user, card_id)

    if title is not None:
        card.title = title
    # description is nullable, so "not provided" and "set to null" are different
    # requests and the caller has to tell them apart for us.
    if description_provided:
        card.description = description

    await session.commit()
    await session.refresh(card)
    return card


async def move_card(
    session: AsyncSession,
    user: User,
    card_id: uuid.UUID,
    target_column_id: uuid.UUID,
    position: int,
) -> Card:
    """Move a card to a column and position, in one transaction.

    Both the card and the target column are fetched through the ownership join,
    so a card cannot be moved into a column the user does not own, and neither id
    is trusted because it arrived in the request.
    """
    card = await get_owned_card(session, user, card_id)
    source_column = await get_owned_column(session, user, card.column_id)
    target_column = await get_owned_column(session, user, target_column_id)

    if target_column.board_id != source_column.board_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="A card cannot be moved to a different board",
        )

    if target_column.id == source_column.id:
        siblings = await list_cards(session, source_column.id)
        ordering.insert_at(siblings, card, position)
    else:
        source_siblings = await list_cards(session, source_column.id)
        target_siblings = await list_cards(session, target_column.id)

        ordering.remove_from(source_siblings, card)
        card.column_id = target_column.id
        ordering.insert_at(target_siblings, card, position)

    await session.commit()
    await session.refresh(card)
    return card


async def delete_card(
    session: AsyncSession, user: User, card_id: uuid.UUID
) -> None:
    card = await get_owned_card(session, user, card_id)
    siblings = await list_cards(session, card.column_id)

    await session.delete(card)
    await session.flush()

    ordering.remove_from(siblings, card)
    await session.commit()
