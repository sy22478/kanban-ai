"""Users, looking them up by email, and the per-account login backoff."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import LOGIN_BACKOFF_CAP, LOGIN_FREE_ATTEMPTS
from app.models import User


def normalise_email(email: str) -> str:
    """Lowercased and trimmed, so one address cannot become two accounts.

    The local part of an address is technically case-sensitive per RFC 5321, and
    essentially no mail provider treats it that way. Honouring the RFC here would
    let someone register Sonu@example.com alongside sonu@example.com, both
    passing the unique index, and it is not clear which of them owns the boards.
    Every comparison and every write goes through this, so the stored form and
    the looked-up form cannot drift apart.
    """
    return email.strip().lower()


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == normalise_email(email)))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, email: str, password_hash: str) -> User:
    """Add a user. Flushed rather than committed so registration can create the
    account and its first session in one transaction."""
    user = User(email=normalise_email(email), password_hash=password_hash)
    db.add(user)
    await db.flush()
    return user


def backoff_after(failed_count: int) -> timedelta | None:
    """How long to lock an account after this many consecutive failures.

    The first few are free, because the commonest cause of a failed login is its
    owner mistyping. After that the delay doubles, which costs a guessing attack
    far more than it costs a person: someone who has genuinely forgotten waits
    seconds, while an attacker's thousandth attempt is fifteen minutes away.

    Capped, rather than doubling forever, so a hostile third party cannot lock a
    real person out of their account indefinitely just by failing to log in as
    them. That is the trade-off account lockout always makes, and an uncapped
    version turns it into a denial of service against the user.
    """
    if failed_count <= LOGIN_FREE_ATTEMPTS:
        return None
    # The exponent is clamped before it is used, not after. 2 ** 194 is a
    # perfectly good Python integer and timedelta cannot hold it: an account with
    # a few hundred failures raised OverflowError here, which login would have
    # answered with a 500 while every other bad login answered 401. That
    # difference is exactly the enumeration oracle the generic 401 exists to
    # close, arriving through the code meant to slow guessing down.
    doublings = min(failed_count - LOGIN_FREE_ATTEMPTS - 1, 30)
    return min(timedelta(seconds=2**doublings), LOGIN_BACKOFF_CAP)


def is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > datetime.now(UTC)


def record_failed_login(user: User) -> None:
    """Count a failure and lock if the count has earned it.

    Does not commit: the caller decides the transaction.
    """
    user.failed_login_count += 1
    backoff = backoff_after(user.failed_login_count)
    if backoff is not None:
        user.locked_until = datetime.now(UTC) + backoff


def record_successful_login(user: User) -> None:
    """Clear the backoff. Getting the password right is the proof of ownership
    that the counter existed to demand."""
    user.failed_login_count = 0
    user.locked_until = None
