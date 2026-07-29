import uuid

from fastapi import APIRouter, status

from app.deps import CurrentUser, SessionDep
from app.schemas import CardCreate, CardMove, CardRead, CardUpdate
from app.services import cards
from app.services.columns import get_owned_column

router = APIRouter(prefix="/api", tags=["cards"])


@router.get("/columns/{column_id}/cards", response_model=list[CardRead])
async def list_cards(column_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    column = await get_owned_column(session, user, column_id)
    return await cards.list_cards(session, column.id)


@router.post(
    "/columns/{column_id}/cards",
    response_model=CardRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_card(
    column_id: uuid.UUID, body: CardCreate, session: SessionDep, user: CurrentUser
):
    return await cards.create_card(
        session, user, column_id, body.title, body.description
    )


@router.patch("/cards/{card_id}", response_model=CardRead)
async def update_card(
    card_id: uuid.UUID, body: CardUpdate, session: SessionDep, user: CurrentUser
):
    return await cards.update_card(
        session,
        user,
        card_id,
        body.title,
        body.description,
        description_provided="description" in body.model_fields_set,
    )


@router.patch("/cards/{card_id}/move", response_model=CardRead)
async def move_card(
    card_id: uuid.UUID, body: CardMove, session: SessionDep, user: CurrentUser
):
    return await cards.move_card(session, user, card_id, body.column_id, body.position)


@router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(card_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    await cards.delete_card(session, user, card_id)
