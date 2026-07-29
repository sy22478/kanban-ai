import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Board, BoardColumn, User


async def get_owned_board(
    session: AsyncSession,
    user: User,
    board_id: uuid.UUID,
    *,
    with_contents: bool = False,
) -> Board:
    """Fetch a board the user owns, or raise 404.

    The owner_id filter is part of the query rather than a check afterwards.
    That is the difference between tenant isolation and a reminder to check.

    404 and not 403: 403 tells the caller the board exists and belongs to
    somebody else, which is a small information leak and an invitation.
    """
    query = select(Board).where(Board.id == board_id, Board.owner_id == user.id)
    if with_contents:
        query = query.options(
            selectinload(Board.columns).selectinload(BoardColumn.cards)
        )

    board = (await session.execute(query)).scalar_one_or_none()
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Board not found")
    return board


async def list_boards(session: AsyncSession, user: User) -> list[Board]:
    result = await session.execute(
        select(Board).where(Board.owner_id == user.id).order_by(Board.created_at)
    )
    return list(result.scalars())


async def create_board(session: AsyncSession, user: User, title: str) -> Board:
    board = Board(owner_id=user.id, title=title)
    session.add(board)
    await session.commit()
    await session.refresh(board)
    return board


async def rename_board(
    session: AsyncSession, user: User, board_id: uuid.UUID, title: str
) -> Board:
    board = await get_owned_board(session, user, board_id)
    board.title = title
    await session.commit()
    await session.refresh(board)
    return board


async def delete_board(
    session: AsyncSession, user: User, board_id: uuid.UUID
) -> None:
    board = await get_owned_board(session, user, board_id)
    await session.delete(board)
    await session.commit()
