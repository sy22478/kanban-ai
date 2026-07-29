import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ordering
from app.models import Board, BoardColumn, User
from app.services.boards import get_owned_board


async def list_columns(
    session: AsyncSession, board_id: uuid.UUID
) -> list[BoardColumn]:
    result = await session.execute(
        select(BoardColumn)
        .where(BoardColumn.board_id == board_id)
        .order_by(BoardColumn.position)
    )
    return list(result.scalars())


async def get_owned_column(
    session: AsyncSession, user: User, column_id: uuid.UUID
) -> BoardColumn:
    """Fetch a column the user owns, or raise 404.

    Reached by joining through boards. A column is never looked up by its own id
    alone, because its id says nothing about who may touch it.
    """
    result = await session.execute(
        select(BoardColumn)
        .join(Board, BoardColumn.board_id == Board.id)
        .where(BoardColumn.id == column_id, Board.owner_id == user.id)
    )
    column = result.scalar_one_or_none()
    if column is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Column not found")
    return column


async def create_column(
    session: AsyncSession, user: User, board_id: uuid.UUID, title: str
) -> BoardColumn:
    board = await get_owned_board(session, user, board_id)
    siblings = await list_columns(session, board.id)

    column = BoardColumn(board_id=board.id, title=title, position=len(siblings))
    session.add(column)
    await session.commit()
    await session.refresh(column)
    return column


async def rename_column(
    session: AsyncSession, user: User, column_id: uuid.UUID, title: str
) -> BoardColumn:
    column = await get_owned_column(session, user, column_id)
    column.title = title
    await session.commit()
    await session.refresh(column)
    return column


async def move_column(
    session: AsyncSession, user: User, column_id: uuid.UUID, position: int
) -> BoardColumn:
    column = await get_owned_column(session, user, column_id)
    siblings = await list_columns(session, column.board_id)

    ordering.insert_at(siblings, column, position)
    await session.commit()
    await session.refresh(column)
    return column


async def delete_column(
    session: AsyncSession, user: User, column_id: uuid.UUID
) -> None:
    column = await get_owned_column(session, user, column_id)
    siblings = await list_columns(session, column.board_id)

    await session.delete(column)
    # Flush the delete before renumbering so the remaining rows are the only ones
    # left holding positions.
    await session.flush()

    ordering.remove_from(siblings, column)
    await session.commit()
