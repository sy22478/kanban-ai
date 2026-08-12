"""Rate limiting, both kinds.

They are separate controls doing separate jobs and each is tested on its own:

- **Per-IP, via slowapi.** Rejects before the handler runs, so it is what stands
  between the API and 64 MiB of Argon2 per concurrent attempt. Answers 429.
- **Per-account backoff.** Survives an attacker rotating addresses, which per-IP
  cannot see at all. Answers the same 401 as any other failed login, on purpose.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.config import LOGIN_FREE_ATTEMPTS
from app.limiter import limiter
from app.services.users import backoff_after
from tests.conftest import PASSWORD, login, register

EMAIL = "someone@example.com"
WRONG = "definitely not the password"


def test_the_first_attempts_are_free():
    """Someone mistyping their own password is not locked out."""
    for attempt in range(1, LOGIN_FREE_ATTEMPTS + 1):
        assert backoff_after(attempt) is None


def test_the_backoff_doubles():
    first = backoff_after(LOGIN_FREE_ATTEMPTS + 1)
    second = backoff_after(LOGIN_FREE_ATTEMPTS + 2)
    third = backoff_after(LOGIN_FREE_ATTEMPTS + 3)

    assert second == first * 2
    assert third == second * 2


def test_the_backoff_is_capped():
    """Uncapped doubling would let a stranger lock a real person out of their
    account permanently, just by failing to log in as them."""
    assert backoff_after(200) == backoff_after(100)
    assert backoff_after(200) <= timedelta(minutes=15)


async def test_repeated_failures_lock_the_account(client, session):
    await register(client, EMAIL)

    for _ in range(LOGIN_FREE_ATTEMPTS + 1):
        assert (await login(client, EMAIL, password=WRONG)).status_code == 401

    locked_until = (
        await session.execute(text("select locked_until from users"))
    ).scalar_one()
    assert locked_until is not None
    assert locked_until > datetime.now(UTC)


async def test_the_correct_password_is_refused_while_locked(client, session):
    """What makes it a lockout rather than a message. If the right password still
    worked, the counter would be decoration."""
    await register(client, EMAIL)
    for _ in range(LOGIN_FREE_ATTEMPTS + 1):
        await login(client, EMAIL, password=WRONG)

    response = await login(client, EMAIL)

    assert response.status_code == 401


async def test_a_locked_account_answers_exactly_like_a_wrong_password(client):
    """The lockout must not announce itself.

    A 423 or a 429 here would tell an attacker that the account exists and that
    their guessing is being counted, which is the enumeration leak the generic
    401 exists to prevent. Status and body both.
    """
    await register(client, EMAIL)
    await register(client, "other@example.com")

    for _ in range(LOGIN_FREE_ATTEMPTS + 1):
        await login(client, EMAIL, password=WRONG)

    locked = await login(client, EMAIL)
    ordinary = await login(client, "other@example.com", password=WRONG)
    unknown = await login(client, "nobody@example.com", password=WRONG)

    assert locked.status_code == ordinary.status_code == unknown.status_code == 401
    assert locked.json() == ordinary.json() == unknown.json()


async def test_the_lock_expires(client, session):
    await register(client, EMAIL)
    for _ in range(LOGIN_FREE_ATTEMPTS + 1):
        await login(client, EMAIL, password=WRONG)
    assert (await login(client, EMAIL)).status_code == 401

    await session.execute(
        text("update users set locked_until = now() - interval '1 minute'")
    )
    await session.commit()

    assert (await login(client, EMAIL)).status_code == 200


async def test_a_successful_login_clears_the_counter(client, session):
    await register(client, EMAIL)
    for _ in range(LOGIN_FREE_ATTEMPTS - 1):
        await login(client, EMAIL, password=WRONG)

    assert (await login(client, EMAIL)).status_code == 200

    count = (
        await session.execute(text("select failed_login_count from users"))
    ).scalar_one()
    assert count == 0


async def test_failures_against_one_account_do_not_lock_another(client, session):
    """Scoped to the account. A counter that locked everyone would pass the
    lockout tests above and be a denial of service."""
    await register(client, EMAIL)
    await register(client, "other@example.com")

    for _ in range(LOGIN_FREE_ATTEMPTS + 1):
        await login(client, EMAIL, password=WRONG)

    assert (await login(client, "other@example.com")).status_code == 200


async def test_the_per_ip_limit_answers_429(client):
    """The control against the Argon2 memory DoS. It fires before the handler,
    which is the whole point: a 401 has already paid the 65ms."""
    await register(client, EMAIL)

    statuses = []
    for _ in range(15):
        statuses.append((await login(client, EMAIL, password=WRONG)).status_code)

    assert 429 in statuses, statuses
    # And it was not 429 from the very first attempt, which would mean the limit
    # is set so low the endpoint is unusable.
    assert statuses[0] == 401


async def test_the_limiter_is_reset_between_tests(client):
    """The previous test drove the login limit to its ceiling. If the autouse
    reset fixture were not working, this would be 429 and every later test in
    the run would fail for an unrelated reason."""
    await register(client, EMAIL)

    assert (await login(client, EMAIL)).status_code == 200


async def test_the_register_limit_answers_429(client):
    """Registration has its own per-IP ceiling, and nothing asserted it.

    It is the only bound on an unauthenticated endpoint that performs a 64 MiB
    Argon2id hash per call, so removing the decorator changed no test while
    opening the same memory-exhaustion vector the login limit exists to close.
    An attacker does not need an account to reach this one.

    Distinct addresses on purpose: repeating one would be answered 409 and would
    prove only that duplicates are counted. The autouse reset fixture clears the
    counter afterwards, so this does not poison what follows.
    """
    statuses = []
    for attempt in range(25):
        response = await register(client, f"flood{attempt}@example.com")
        statuses.append(response.status_code)

    assert 429 in statuses, statuses
    # And not from the first attempt, which would mean nobody can register at all.
    assert statuses[0] == 201
