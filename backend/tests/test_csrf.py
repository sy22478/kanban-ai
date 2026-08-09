"""The CSRF checks.

Every row of the matrix is its own test. A single test that posted three bad
content types and asserted "rejected" would pass while two of them sailed
through, which is the failure mode DECISIONS.md recorded on 2026-08-01.

The client fixture sends the custom header by default, so the tests that check
the header requirement strip it deliberately.
"""

import pytest

from app.config import CSRF_HEADER, FORBIDDEN_CONTENT_TYPES, settings
from tests.conftest import PASSWORD, register, without_csrf

EMAIL = "someone@example.com"

BODY = {"title": "A board"}


async def test_a_correct_write_succeeds(client):
    """The positive control. Every rejection test below is meaningless without
    it: if writes were broken outright, they would all pass."""
    await register(client, EMAIL)

    response = await client.post("/api/boards", json=BODY)

    assert response.status_code == 201


async def test_a_write_without_the_custom_header_is_refused(client):
    await register(client, EMAIL)

    response = await without_csrf(client, "POST", "/api/boards", json=BODY)

    assert response.status_code == 403


async def test_the_header_is_required_even_with_a_valid_session(client, session):
    """The point of the check. The attacker's page has the victim's cookie
    attached for free; what it cannot do is set this header."""
    await register(client, EMAIL)

    response = await without_csrf(client, "POST", "/api/boards", json=BODY)

    assert response.status_code == 403
    # And nothing was written.
    boards = await client.get("/api/boards")
    assert boards.json() == []


@pytest.mark.parametrize("content_type", FORBIDDEN_CONTENT_TYPES)
async def test_each_form_content_type_is_refused(client, content_type):
    """One test per type rather than one test naming three. These are the three
    a cross-site form can send without triggering a preflight, so each is its own
    bypass."""
    await register(client, EMAIL)

    response = await client.post(
        "/api/boards",
        content=b'{"title": "A board"}',
        headers={"content-type": content_type},
    )

    assert response.status_code == 415


async def test_a_form_content_type_with_a_charset_is_still_refused(client):
    """text/plain; charset=utf-8 is text/plain. Matching the raw header instead
    of the media type would let this through."""
    await register(client, EMAIL)

    response = await client.post(
        "/api/boards",
        content=b'{"title": "A board"}',
        headers={"content-type": "text/plain; charset=utf-8"},
    )

    assert response.status_code == 415


async def test_a_write_from_another_origin_is_refused(client):
    await register(client, EMAIL)

    response = await client.post(
        "/api/boards", json=BODY, headers={"origin": "https://evil.example"}
    )

    assert response.status_code == 403


async def test_a_write_from_our_own_origin_is_allowed(client):
    """The other half. A rule that rejected every Origin would pass the test
    above and break the actual application."""
    await register(client, EMAIL)

    response = await client.post(
        "/api/boards", json=BODY, headers={"origin": settings.allowed_origin}
    )

    assert response.status_code == 201


async def test_a_referer_from_another_origin_is_refused(client):
    await register(client, EMAIL)

    response = await client.post(
        "/api/boards",
        json=BODY,
        headers={"referer": "https://evil.example/some/page"},
    )

    assert response.status_code == 403


async def test_a_referer_from_our_own_origin_is_allowed(client):
    await register(client, EMAIL)

    response = await client.post(
        "/api/boards",
        json=BODY,
        headers={"referer": f"{settings.allowed_origin}/boards"},
    )

    assert response.status_code == 201


async def test_origin_wins_over_referer(client):
    """Origin is authoritative. A hostile Origin with a friendly Referer must
    still be refused, or the fallback becomes the bypass."""
    await register(client, EMAIL)

    response = await client.post(
        "/api/boards",
        json=BODY,
        headers={
            "origin": "https://evil.example",
            "referer": f"{settings.allowed_origin}/boards",
        },
    )

    assert response.status_code == 403


async def test_login_is_also_protected(client):
    """Login CSRF is a real attack: it signs the victim into the attacker's
    account so that everything they then do is recorded there."""
    response = await without_csrf(
        client, "POST", "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 403


async def test_every_state_changing_verb_is_covered(client):
    """PATCH and DELETE, not just POST. A guard that only looked at POST would
    leave the rest of the API open."""
    await register(client, EMAIL)
    board = (await client.post("/api/boards", json=BODY)).json()

    patch = await without_csrf(
        client, "PATCH", f"/api/boards/{board['id']}", json={"title": "Renamed"}
    )
    delete = await without_csrf(client, "DELETE", f"/api/boards/{board['id']}")

    assert patch.status_code == 403
    assert delete.status_code == 403
    # Untouched by either attempt.
    assert (await client.get(f"/api/boards/{board['id']}")).json()["title"] == "A board"


async def test_reads_do_not_need_the_header(client):
    """GET is exempt, which is only safe because no GET mutates. That invariant
    is checked directly in test_no_get_route_mutates below."""
    await register(client, EMAIL)

    response = await without_csrf(client, "GET", "/api/boards")

    assert response.status_code == 200


def test_no_get_route_mutates():
    """The invariant the GET exemption rests on.

    A GET that changes state is reachable from an <img src> on any page on the
    internet, with the victim's cookie attached and no header required. This
    walks the actual route table rather than trusting a convention: every
    non-safe verb must live on a route whose handler is not also a GET, and no
    GET handler may call into a service function that writes.
    """
    import inspect

    from fastapi.routing import APIRoute

    from app.main import app
    from app.services import boards, cards, columns, users

    writers = {
        name
        for module in (boards, cards, columns, users)
        for name, function in vars(module).items()
        if inspect.iscoroutinefunction(function)
        and any(
            verb in name
            for verb in ("create", "update", "rename", "move", "delete")
        )
    }
    assert writers, "found no writing service functions, so this proves nothing"

    def walk(routes):
        """Flatten the route table.

        FastAPI 0.140 does not splice an included router's routes into
        app.routes; it stores a _IncludedRouter wrapper holding the original.
        Iterating app.routes alone therefore finds none of the application's
        real endpoints, which would make this test pass by looking at nothing.
        """
        for route in routes:
            if isinstance(route, APIRoute):
                yield route
            inner = getattr(route, "original_router", None)
            if inner is not None:
                yield from walk(inner.routes)

    all_routes = list(walk(app.routes))
    get_routes = [
        route for route in all_routes if route.methods <= {"GET", "HEAD"}
    ]
    assert get_routes, "found no GET routes, so this proves nothing"
    # /api/me, the board list, one board, its columns, a column's cards.
    assert len(get_routes) >= 5, f"only found {len(get_routes)} GET routes"

    offenders = [
        (route.path, writer)
        for route in get_routes
        for writer in writers
        if f".{writer}(" in inspect.getsource(route.endpoint)
    ]

    assert offenders == [], f"GET routes calling a writing service: {offenders}"
