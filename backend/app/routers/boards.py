import uuid

from fastapi import APIRouter, status

from app.deps import CurrentUser, SessionDep
from app.schemas import BoardCreate, BoardDetail, BoardRead, BoardUpdate
from app.services import boards

router = APIRouter(prefix="/api/boards", tags=["boards"])


@router.get("", response_model=list[BoardRead])
async def list_boards(session: SessionDep, user: CurrentUser):
    return await boards.list_boards(session, user)


@router.post("", response_model=BoardRead, status_code=status.HTTP_201_CREATED)
async def create_board(body: BoardCreate, session: SessionDep, user: CurrentUser):
    return await boards.create_board(session, user, body.title)


@router.get("/{board_id}", response_model=BoardDetail)
async def get_board(board_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await boards.get_owned_board(session, user, board_id, with_contents=True)


@router.patch("/{board_id}", response_model=BoardRead)
async def rename_board(
    board_id: uuid.UUID, body: BoardUpdate, session: SessionDep, user: CurrentUser
):
    return await boards.rename_board(session, user, board_id, body.title)


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(board_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    await boards.delete_board(session, user, board_id)
