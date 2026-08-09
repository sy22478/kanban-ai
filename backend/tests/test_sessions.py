"""Session lifetime rules.

Timestamps are moved in the database rather than waited for. A test that sleeps
for a real idle timeout either takes fourteen days or proves something smaller
than it claims.

One property per test. A single test asserting "expiry works" would pass while
only one of the two expiries did, and the one usually missing is the absolute
cap, because a sliding window looks like it is doing the job.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.models import UserSession
from app.services import sessions


async def shift(db, token_owner_email, **delta):
    """Move a session's timestamps, as if time had passed."""
    await db.execute(
        text(
            "update sessions set last_used_at = last_used_at + :used,"
            " expires_at = expires_at + :expires"
            " where user_id = (select id from users where email = :email)"
        ),
        {
            "used": timedelta(**delta.get("last_used", {})),
            "expires": timedelta(**delta.get("expires", {})),
            "email": token_owner_email,
        },
    )
    await db.commit()


async def last_used_at(db, email):
    result = await db.execute(
        text(
            "select last_used_at from sessions"
            " where user_id = (select id from users where email = :email)"
        ),
        {"email": email},
    )
    return result.scalar_one()


async def test_the_token_is_never_stored(session, user):
    token = await sessions.create_session(session, user, "pytest")
    await session.commit()

    stored = (await session.execute(select(UserSession.token_hash))).scalar_one()

    assert token.encode() not in stored
    assert stored != token.encode()
    # And the digest is what is actually there, so lookups can still work.
    assert len(stored) == 32


async def test_a_fresh_session_resolves_to_its_user(session, user):
    """The positive control. Without it every test below could pass because
    lookups never work at all."""
    token = await sessions.create_session(session, user, "pytest")
    await session.commit()

    found = await sessions.user_for_token(session, token)

    assert found is not None
    assert found.id == user.id


async def test_an_unknown_token_resolves_to_nobody(session, user):
    await sessions.create_session(session, user, "pytest")
    await session.commit()

    assert await sessions.user_for_token(session, "not a real token") is None


async def test_a_session_idle_past_the_window_is_refused(session, user):
    token = await sessions.create_session(session, user, "pytest")
    await session.commit()

    # 15 days since last use, against a 14-day idle window.
    await shift(session, user.email, last_used={"days": -15})

    assert await sessions.user_for_token(session, token) is None


async def test_a_busy_session_still_dies_at_the_absolute_cap(session, user):
    """The one a sliding-only implementation gets wrong.

    Used one second ago, so the idle window is wide open, but created 91 days
    ago against a 90-day cap. If only the idle rule were enforced this session
    would live forever, which is precisely the property that makes a stolen
    token valuable.
    """
    token = await sessions.create_session(session, user, "pytest")
    await session.commit()

    await shift(session, user.email, expires={"days": -91})

    assert await sessions.user_for_token(session, token) is None


async def test_last_used_at_is_not_rewritten_on_every_lookup(session, user):
    token = await sessions.create_session(session, user, "pytest")
    await session.commit()
    before = await last_used_at(session, user.email)

    await sessions.user_for_token(session, token)

    assert await last_used_at(session, user.email) == before


async def test_last_used_at_is_rewritten_once_it_is_stale(session, user):
    """The other half of the throttle. Without this the idle window would never
    slide and every session would expire 14 days after it was created."""
    token = await sessions.create_session(session, user, "pytest")
    await session.commit()

    await shift(session, user.email, last_used={"minutes": -2})
    stale = await last_used_at(session, user.email)

    await sessions.user_for_token(session, token)
    touched = await last_used_at(session, user.email)
    assert touched > stale

    # And immediately again: now fresh, so no second write.
    await sessions.user_for_token(session, token)
    assert await last_used_at(session, user.email) == touched


async def test_logout_removes_the_session(session, user):
    token = await sessions.create_session(session, user, "pytest")
    await session.commit()
    assert await sessions.user_for_token(session, token) is not None

    await sessions.delete_session(session, token)
    await session.commit()

    assert await sessions.user_for_token(session, token) is None


async def test_purge_removes_this_users_dead_sessions(session, user):
    token = await sessions.create_session(session, user, "pytest")
    await session.commit()
    await shift(session, user.email, expires={"days": -91})

    await sessions.purge_expired_for_user(session, user.id)
    await session.commit()

    assert (await session.execute(select(UserSession))).first() is None


async def test_purge_leaves_a_live_session_alone(session, user):
    """A purge that removed everything would also pass the test above."""
    token = await sessions.create_session(session, user, "pytest")
    await session.commit()

    await sessions.purge_expired_for_user(session, user.id)
    await session.commit()

    assert await sessions.user_for_token(session, token) is not None


async def test_purge_does_not_touch_another_users_sessions(
    session, user, other_user
):
    """Scoped to one user. The login path runs this, and one person logging in
    has no business deleting rows belonging to anyone else."""
    theirs = await sessions.create_session(session, other_user, "pytest")
    await session.commit()
    await shift(session, other_user.email, expires={"days": -91})

    await sessions.purge_expired_for_user(session, user.id)
    await session.commit()

    # Their session is expired, so it does not resolve, but the row survives:
    # it was not this user's to delete.
    remaining = (await session.execute(select(UserSession.user_id))).scalars().all()
    assert remaining == [other_user.id]


async def test_a_user_agent_too_long_for_the_column_does_not_fail_the_login(
    session, user
):
    token = await sessions.create_session(session, user, "u" * 5000)
    await session.commit()

    assert await sessions.user_for_token(session, token) is not None


async def test_deleting_the_user_deletes_their_sessions(session, user):
    """The database-level cascade, exercised through the ORM rather than assumed
    from the schema."""
    await sessions.create_session(session, user, "pytest")
    await session.commit()

    await session.delete(user)
    await session.commit()

    assert (await session.execute(select(UserSession))).first() is None
