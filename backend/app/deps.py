from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SESSION_COOKIE
from app.db import get_session
from app.models import User
from app.services import sessions

SessionDep = Annotated[AsyncSession, Depends(get_session)]

NOT_AUTHENTICATED = "Not authenticated"


async def get_current_user(request: Request, db: SessionDep) -> User:
    """The user the request acts as.

    This is the only place in the application that decides who the current user
    is. In phase 1 it returned the seeded user; phase 2 changes this body to read
    the session cookie and nothing that depends on it had to change. That was the
    claim phase 1 made, and this is it being paid off.

    Everything downstream still receives a User, so every ownership filter in
    app/services keeps working untouched. Authentication decides who you are;
    those filters decide what you can reach. Collapsing the two is how an
    authenticated user ends up able to read everyone's data.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOT_AUTHENTICATED)

    user = await sessions.user_for_token(db, token)
    if user is None:
        # Expired, revoked, or never real. All the same answer: a distinction
        # here would tell the holder of a stolen token which it was.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOT_AUTHENTICATED)

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
