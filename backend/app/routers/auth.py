"""Registration, login and logout.

The request bodies here contain plaintext passwords, so nothing in this module
logs a body, and no exception handler anywhere should either. One
logger.info(body) is all it takes to put every user's password in the logs.
"""

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError

from app.config import (
    LOGIN_RATE_LIMIT,
    REGISTER_RATE_LIMIT,
    SESSION_ABSOLUTE_LIFETIME,
    SESSION_COOKIE,
)
from app.deps import SessionDep
from app.limiter import limiter
from app.schemas import LoginRequest, RegisterRequest, UserRead
from app.security import DUMMY_HASH, hash_password, verify_password
from app.services import sessions, users

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One message for every way a login can fail: no such address, wrong password,
# account in backoff. Same status, same body, same shape. The status code is
# itself a discrepancy factor, so a locked account must not answer 423 or 429 --
# that would confirm the account exists, which is the thing being protected.
INVALID_CREDENTIALS = "Incorrect email address or password"


def set_session_cookie(response: Response, token: str) -> None:
    """Attach the session cookie.

    __Host- is a prefix the browser enforces: it refuses to store a cookie by
    that name unless Secure is set, Path is /, and there is no Domain attribute.
    No Domain means no sibling subdomain can set or overwrite it, which is the
    subdomain-forgery hole that a plain cookie name leaves open.

    Secure is set unconditionally rather than branched on an environment flag,
    because browsers treat http://localhost as a secure context, so it works in
    development, and a flag that disables it is a flag that can be wrong in
    production.

    max_age is a courtesy to the browser and is not the control. Expiry is
    enforced server-side from the sessions table, because a client is free to
    ignore max_age and keep sending the cookie forever.
    """
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_ABSOLUTE_LIFETIME.total_seconds()),
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Delete the cookie, with the attributes it was set with.

    A delete_cookie whose path or security attributes differ from the original
    does not match it, and the browser keeps the old one.
    """
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, secure=True, samesite="strict", path="/"
    )


@router.post(
    "/register", response_model=UserRead, status_code=status.HTTP_201_CREATED
)
@limiter.limit(REGISTER_RATE_LIMIT)
async def register(
    body: RegisterRequest, request: Request, response: Response, db: SessionDep
):
    """Create an account and sign it in.

    This endpoint tells the caller whether an address is already registered, and
    that is a deliberate, logged decision rather than an oversight. Hiding it
    means answering 201 to a duplicate without creating anything, and with no
    password reset in this phase that leaves someone who re-registers their own
    address unable to log in and with no way back. Login stays enumeration-flat,
    which is where an attacker actually works at scale.
    """
    email = users.normalise_email(body.email)

    if await users.get_by_email(db, email) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="That email address is already registered"
        )

    password_hash = await asyncio.to_thread(hash_password, body.password)
    user = await users.create_user(db, email, password_hash)
    token = await sessions.create_session(
        db, user, request.headers.get("user-agent")
    )

    try:
        await db.commit()
    except IntegrityError:
        # Two registrations of the same address racing between the check above
        # and this commit. The unique index is the real guard; this turns the
        # loser into the same 409 the check would have given rather than a 500.
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="That email address is already registered"
        ) from None

    set_session_cookie(response, token)
    return user


@router.post("/login", response_model=UserRead)
@limiter.limit(LOGIN_RATE_LIMIT)
async def login(
    body: LoginRequest, request: Request, response: Response, db: SessionDep
):
    """Sign in.

    Two things here are easy to get wrong and are the point of the shape below.

    **Timing.** Every path performs exactly one Argon2 verify, against DUMMY_HASH
    when there is no such user. Returning early for an unknown address would make
    that response arrive in microseconds while a real one takes ~65ms, and that
    difference is a user-enumeration oracle regardless of how identical the
    response body is.

    **The event loop.** An Argon2id verify at 64 MiB is roughly 65ms of solid
    CPU. Run directly in an async handler it blocks the entire loop, so every
    other request in flight waits behind it. asyncio.to_thread moves it to the
    threadpool. The alternative in circulation -- a sync `def` handler, which
    FastAPI threadpools automatically -- cannot work here: a threadpooled sync
    function cannot await, and every one of these endpoints needs the async
    database session.
    """
    email = users.normalise_email(body.email)
    user = await users.get_by_email(db, email)
    locked = user is not None and users.is_locked(user)

    # DUMMY_HASH for both the unknown account and the locked one. Skipping the
    # hash when locked would make that path return in microseconds, so an
    # attacker could learn "this account exists and I have already triggered its
    # lockout" from the response time alone -- reintroducing the enumeration leak
    # through the defence meant to stop the guessing.
    to_check = user.password_hash if user is not None and not locked else DUMMY_HASH
    ok, rehashed = await asyncio.to_thread(verify_password, body.password, to_check)

    if user is None or locked or not ok:
        if user is not None and not locked:
            # Not counted while already locked: an attacker should not be able to
            # extend a real person's lockout indefinitely by continuing to fail.
            users.record_failed_login(user)
            await db.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS
        )

    users.record_successful_login(user)

    if rehashed is not None:
        # The parameters have been raised since this password was last hashed.
        # Upgrading it here is the only moment the plaintext is available.
        user.password_hash = rehashed

    # Session fixation: whatever session the caller arrived holding is discarded
    # rather than reused, so a token planted before login is not the token that
    # ends up authenticated.
    presented = request.cookies.get(SESSION_COOKIE)
    if presented is not None:
        await sessions.delete_session(db, presented)

    # Self-cleaning, with no cron job: the users who accumulate dead sessions are
    # exactly the users who log in.
    await sessions.purge_expired_for_user(db, user.id)

    token = await sessions.create_session(db, user, request.headers.get("user-agent"))
    await db.commit()

    set_session_cookie(response, token)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: SessionDep):
    """End this session.

    Deliberately does not require a valid session. Someone holding an expired or
    unknown cookie should still be able to clear it, and answering 401 here would
    leave them stuck with a cookie they cannot get rid of. It is idempotent: 204
    whether or not anything was deleted.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if token is not None:
        await sessions.delete_session(db, token)
        await db.commit()

    clear_session_cookie(response)
