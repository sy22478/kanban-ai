"""Server-side sessions.

The cookie carries an opaque random token. The database stores only its sha256
digest, so the sessions table is not a list of usable credentials. Everything
about whether a session is still valid is decided here, on the server, from
columns -- never from anything the client sends. A cookie's own Max-Age is a
suggestion the browser may ignore and an attacker can simply not honour.

Two expiries, per OWASP, because they catch different things:

- **Absolute** (expires_at) is set at login and never extended. It bounds how
  long a stolen token is worth anything, however actively it is used. A
  sliding-only scheme has no such bound: a token being used every day never
  expires, which is exactly the situation an attacker with a stolen token is in.
- **Idle** (last_used_at) closes sessions nobody came back to.

A session must satisfy both.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    SESSION_ABSOLUTE_LIFETIME,
    SESSION_IDLE_LIFETIME,
    SESSION_TOUCH_INTERVAL,
)
from app.models import User, UserSession
from app.security import new_session_token, token_digest


def _now() -> datetime:
    return datetime.now(UTC)


async def create_session(
    db: AsyncSession, user: User, user_agent: str | None
) -> str:
    """Start a session and return its token.

    The token is returned exactly once, to be put in the cookie, and is not
    recoverable afterwards: only its digest is kept. Flushed rather than
    committed so the caller can do this inside a larger transaction, which is
    what login needs in order to rotate and purge atomically.
    """
    token = new_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=token_digest(token),
            expires_at=_now() + SESSION_ABSOLUTE_LIFETIME,
            # Truncated rather than validated. It is a diagnostic, and a header
            # long enough to overflow the column must not be able to fail a
            # login.
            user_agent=user_agent[:512] if user_agent else None,
        )
    )
    await db.flush()
    return token


async def user_for_token(db: AsyncSession, token: str) -> User | None:
    """The user this token authenticates, or None.

    Both expiry conditions are in the WHERE clause rather than checked after the
    row comes back. Same reasoning as the ownership filters in the board
    services: a condition in the query cannot be forgotten by a later edit, and
    an expired session is simply not found rather than found-then-rejected.
    """
    now = _now()
    result = await db.execute(
        select(UserSession, User)
        .join(User, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_digest(token),
            UserSession.expires_at > now,
            UserSession.last_used_at > now - SESSION_IDLE_LIFETIME,
        )
    )
    row = result.first()
    if row is None:
        return None

    user_session, user = row

    # Slide the idle window, but not on every request. A busy session would
    # otherwise turn every read into a write. The cost is that idle expiry is
    # only accurate to within SESSION_TOUCH_INTERVAL, which against a 14-day
    # window is noise.
    if now - user_session.last_used_at >= SESSION_TOUCH_INTERVAL:
        user_session.last_used_at = now
        await db.commit()

    return user


async def delete_session(db: AsyncSession, token: str) -> None:
    """Log out. Flushed, not committed, so it can join the caller's transaction."""
    await db.execute(
        delete(UserSession).where(UserSession.token_hash == token_digest(token))
    )
    await db.flush()


async def purge_expired_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Drop this user's dead sessions.

    Called inside the login transaction, which is what keeps the table
    self-cleaning without a cron job or a background task: the people who
    accumulate sessions are the people who log in.

    Scoped to one user on purpose. A global sweep would touch rows belonging to
    everyone on a path where one person is logging in, and it is not this
    request's business.
    """
    now = _now()
    await db.execute(
        delete(UserSession).where(
            UserSession.user_id == user_id,
            (UserSession.expires_at <= now)
            | (UserSession.last_used_at <= now - SESSION_IDLE_LIFETIME),
        )
    )
    await db.flush()
