from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SEED_USER_EMAIL
from app.db import get_session
from app.models import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(session: SessionDep) -> User:
    """The user the request acts as.

    Phase 1 has no login, so this is the seeded user. This function is the only
    place in the application that decides who the current user is. In phase 2 its
    body changes to read the session, and nothing that depends on it has to
    change, which is the whole reason it exists this early.
    """
    result = await session.execute(select(User).where(User.email == SEED_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="the seeded user is missing; run python -m app.seed",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
