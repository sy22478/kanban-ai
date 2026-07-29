from fastapi import APIRouter, FastAPI
from sqlalchemy import select

from app.deps import CurrentUser, SessionDep
from app.models import User
from app.routers import boards, cards, columns
from app.schemas import UserRead

app = FastAPI(title="Kanban AI")

api = APIRouter(prefix="/api")


@api.get("/users", response_model=list[UserRead])
async def list_users(session: SessionDep) -> list[User]:
    """Phase 0's end-to-end path, kept as a plumbing check. No fallback: with the
    database stopped this raises rather than returning something that looks like
    success."""
    result = await session.execute(select(User).order_by(User.email))
    return list(result.scalars())


@api.get("/me", response_model=UserRead)
async def read_current_user(user: CurrentUser) -> User:
    """Who the request is acting as. In phase 1 always the seeded user."""
    return user


app.include_router(api)
app.include_router(boards.router)
app.include_router(columns.router)
app.include_router(cards.router)
