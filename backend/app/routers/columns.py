import uuid

from fastapi import APIRouter, status

from app.deps import CurrentUser, SessionDep
from app.schemas import ColumnCreate, ColumnMove, ColumnRead, ColumnUpdate
from app.services import columns
from app.services.boards import get_owned_board

router = APIRouter(prefix="/api", tags=["columns"])


@router.get("/boards/{board_id}/columns", response_model=list[ColumnRead])
async def list_columns(board_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    board = await get_owned_board(session, user, board_id)
    return await columns.list_columns(session, board.id)


@router.post(
    "/boards/{board_id}/columns",
    response_model=ColumnRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_column(
    board_id: uuid.UUID, body: ColumnCreate, session: SessionDep, user: CurrentUser
):
    return await columns.create_column(session, user, board_id, body.title)


@router.patch("/columns/{column_id}", response_model=ColumnRead)
async def rename_column(
    column_id: uuid.UUID, body: ColumnUpdate, session: SessionDep, user: CurrentUser
):
    return await columns.rename_column(session, user, column_id, body.title)


@router.patch("/columns/{column_id}/move", response_model=ColumnRead)
async def move_column(
    column_id: uuid.UUID, body: ColumnMove, session: SessionDep, user: CurrentUser
):
    return await columns.move_column(session, user, column_id, body.position)


@router.delete("/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(column_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    await columns.delete_column(session, user, column_id)
