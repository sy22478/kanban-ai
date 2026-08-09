"""Registration, login, logout, and the 401 boundary.

Everything here goes through real HTTP against the real app. No dependency
overrides on get_current_user.
"""

import asyncio
import statistics
import time

import pytest
from sqlalchemy import text

from app.config import SESSION_COOKIE
from tests.conftest import PASSWORD, get_bearing, login, register

EMAIL = "someone@example.com"


async def test_registration_creates_an_account_and_signs_it_in(client):
    response = await register(client, EMAIL)

    assert response.status_code == 201
    assert response.json()["email"] == EMAIL
    assert SESSION_COOKIE in response.cookies

    # And the session actually works, which the cookie being present does not
    # prove on its own.
    me = await client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL


async def test_the_password_is_never_returned(client):
    response = await register(client, EMAIL)

    body = response.json()
    assert set(body) == {"id", "email"}
    assert PASSWORD not in response.text


async def test_the_password_is_stored_only_as_an_argon2id_hash(client, session):
    await register(client, EMAIL)

    stored = (
        await session.execute(text("select password_hash from users"))
    ).scalar_one()

    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


async def test_the_session_cookie_is_httponly_secure_and_strict(client):
    response = await register(client, EMAIL)

    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    # __Host- requires Secure and Path=/ and forbids Domain. A browser silently
    # drops the cookie if any of those is wrong, so login would appear to work
    # and every request afterwards would be 401.
    assert "Secure" in header
    assert "Path=/" in header
    assert "Domain" not in header
    assert "samesite=strict" in header.lower()


async def test_the_cookie_value_is_not_what_is_in_the_database(client, session):
    response = await register(client, EMAIL)
    token = response.cookies[SESSION_COOKIE]

    stored = (
        await session.execute(text("select token_hash from sessions"))
    ).scalar_one()

    assert token.encode() not in stored


async def test_a_duplicate_registration_is_refused(client):
    await register(client, EMAIL)

    response = await register(client, EMAIL)

    assert response.status_code == 409


async def test_email_case_does_not_create_a_second_account(client):
    await register(client, "Sonu@Example.com")

    response = await register(client, "sonu@example.com")

    assert response.status_code == 409


async def test_registration_rejects_a_short_password(client):
    response = await register(client, EMAIL, password="short")

    assert response.status_code == 422


async def test_registration_rejects_a_malformed_email(client):
    response = await register(client, "not-an-email")

    assert response.status_code == 422


async def test_registration_rejects_an_attempt_to_set_the_id(client):
    """Mass assignment. StrictModel forbids extra fields, so a body that tries to
    choose its own primary key is rejected rather than partially honoured."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "id": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 422


async def test_login_works_and_replaces_the_session(client):
    await register(client, EMAIL)
    first = client.cookies[SESSION_COOKIE]

    response = await login(client, EMAIL)

    assert response.status_code == 200
    second = response.cookies[SESSION_COOKIE]
    # Rotated. Reusing the token the caller arrived with is session fixation.
    assert second != first


async def test_the_session_presented_at_login_is_invalidated(client, session):
    """Rotation has to destroy the old session, not merely stop using it. A
    rotation that leaves the previous row alive has revoked nothing."""
    await register(client, EMAIL)
    old = client.cookies[SESSION_COOKIE]

    await login(client, EMAIL)

    live = (await session.execute(text("select count(*) from sessions"))).scalar_one()
    assert live == 1

    # The old token specifically is dead.
    assert (await get_bearing(client, "/api/me", old)).status_code == 401


async def test_the_wrong_password_is_refused(client):
    await register(client, EMAIL)

    response = await login(client, EMAIL, password="wrong password entirely")

    assert response.status_code == 401


async def test_an_unknown_address_and_a_wrong_password_are_indistinguishable(client):
    """User enumeration. Identical status, identical body. The status code is
    itself a discrepancy factor, so it is asserted rather than assumed."""
    await register(client, EMAIL)

    wrong_password = await login(client, EMAIL, password="wrong password entirely")
    no_such_user = await login(client, "nobody@example.com", password=PASSWORD)

    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json() == no_such_user.json()


async def test_an_unknown_address_costs_the_same_time_as_a_wrong_password(client):
    """The response bodies matching is not enough. Returning early for an unknown
    address makes it arrive in microseconds against ~65ms for a real one, and
    that gap is the enumeration oracle."""
    await register(client, EMAIL)

    async def median_ms(email):
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            await login(client, email, password="wrong password entirely")
            samples.append((time.perf_counter() - start) * 1000)
        return statistics.median(samples)

    real = await median_ms(EMAIL)
    absent = await median_ms("nobody@example.com")

    assert 0.4 < absent / real < 2.5, f"real {real:.1f}ms vs absent {absent:.1f}ms"


async def test_logout_ends_the_session(client, session):
    await register(client, EMAIL)

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert (
        await session.execute(text("select count(*) from sessions"))
    ).scalar_one() == 0


async def test_the_cookie_stops_working_after_logout(client):
    """The row being gone is the mechanism. This is the behaviour, and it is the
    property JWT could not have given without extra machinery."""
    await register(client, EMAIL)
    token = client.cookies[SESSION_COOKIE]

    await client.post("/api/auth/logout")

    assert (await get_bearing(client, "/api/me", token)).status_code == 401


async def test_logout_without_a_session_is_still_fine(client):
    """Someone holding a dead cookie must be able to clear it."""
    assert (await client.post("/api/auth/logout")).status_code == 204


async def test_an_unauthenticated_request_is_401(client):
    assert (await client.get("/api/me")).status_code == 401
    assert (await client.get("/api/boards")).status_code == 401


async def test_a_forged_cookie_is_401(client):
    response = await get_bearing(client, "/api/me", "not-a-real-token")

    assert response.status_code == 401


async def test_an_expired_session_is_401(client, session):
    await register(client, EMAIL)
    assert (await client.get("/api/me")).status_code == 200

    await session.execute(
        text("update sessions set expires_at = now() - interval '1 day'")
    )
    await session.commit()

    assert (await client.get("/api/me")).status_code == 401


async def test_an_idle_session_is_401(client, session):
    await register(client, EMAIL)

    await session.execute(
        text("update sessions set last_used_at = now() - interval '15 days'")
    )
    await session.commit()

    assert (await client.get("/api/me")).status_code == 401


async def test_boards_are_reachable_once_signed_in(client):
    """The positive control for the 401 tests above. Without it, a bug that made
    every request fail would look like excellent security."""
    await register(client, EMAIL)

    response = await client.get("/api/boards")

    assert response.status_code == 200
    assert response.json() == []
