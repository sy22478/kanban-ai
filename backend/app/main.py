from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.schemas import UserRead

app = FastAPI(title="Kanban AI")

api = APIRouter(prefix="/api")


@api.get("/users", response_model=list[UserRead])
async def list_users(session: AsyncSession = Depends(get_session)) -> list[User]:
    """Phase 0's one end-to-end path. No fallback: if Postgres is unreachable this
    raises and the request fails, which is the point. A value on screen therefore
    came from the database."""
    result = await session.execute(select(User).order_by(User.email))
    return list(result.scalars())


app.include_router(api)
