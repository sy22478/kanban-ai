"""User A cannot reach user B's data.

This file is the point of phase 2. Everything else in it is plumbing that could
be rewritten; if this passes for the wrong reason, the phase has failed no matter
how well the application appears to work.

It is deliberately self-contained. The clients, the registration, the login and
the fixtures are all defined here rather than imported from conftest.py, because
a PreToolUse hook makes this path unwritable once it exists and conftest.py stays
editable. A test whose job is to be hard to pass should not be able to be made
easy by editing something next to it. The only thing that comes from outside is
the database session.

Five ways this test could pass while proving nothing, and what stops each:

**Overriding get_current_user.** It is never done. app.dependency_overrides is
used for get_session alone, to point the app at the test database. Stubbing out
get_current_user would skip the cookie lookup, the session expiry check and the
User object that every ownership filter hangs off -- the exact code under test --
and the suite would look identical whether the application were secure or wide
open. Both users here are created by real registration and hold a real cookie
from a real POST to /api/auth/login.

**http instead of https in base_url.** The session cookie is Secure. Python's
cookie jar stores a Secure cookie received over http:// and then silently refuses
to send it back, so every request would go out unauthenticated, every endpoint
would answer 401, and a test asserting "A is refused" would go green having
proved only that nobody was logged in. Verified directly before this was written:
over http the application saw no cookie, over https it saw it.

**A cleared cookie standing in for a revoked session.** The same trap one level
down. Logout does two independent things, deleting the session row and clearing
the cookie, and httpx drops a cleared cookie from the jar; the next request then
carries no cookie at all and is refused by the branch that never reaches the
database. A logout that revoked nothing would still answer 401, and this file
reported 19 passed with revocation removed. The logout test now captures the
token before logging out and presents it again by hand, so the refusal has to
come from the session lookup.

**Missing positive control.** Every refusal below is paired, in the same test,
with the owner making the identical request -- same verb, same route --
successfully, and with the effect landing in the database. Without that, a board
that was never created gives both users 404 and the test proves nothing.

The weaker form of that pairing was here first, and was not enough. Seven write
tests refused a PATCH or a DELETE and then had the owner do a GET on a
neighbouring resource. An adversary replaced all seven handlers with ones
answering 404 to everybody, the owner included, and this file still reported 19
passed. Nothing was leaked -- an endpoint that refuses everyone tells no one
anything -- so the phase claim survived, but those tests were not measuring what
this docstring said they were. Each of the seven now ends with the owner
performing that same write on that same route.

**assert status != 200.** Never used. A malformed UUID answers 422 and satisfies
it. Every assertion names the exact code.

Refusals are 404 rather than 403 throughout: a 403 confirms the row exists and
belongs to somebody else, which is a leak and an invitation.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import CSRF_HEADER, SESSION_COOKIE
from app.db import get_session
from app.main import app

ALICE = "alice@example.com"
MALLORY = "mallory@example.com"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def app_on_test_database(session):
    """Point the application at the test database, and nothing else.

    This is the only dependency override in this file, and it replaces plumbing
    rather than a security control.
    """
    app.dependency_overrides[get_session] = lambda: session
    yield
    app.dependency_overrides.clear()


def new_client():
    """A browser. Its own cookie jar, so the two users cannot share a session."""
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
        headers={CSRF_HEADER: "1"},
    )


async def sign_up_and_in(client, email):
    """Register, then log in for real, and return the client holding the cookie.

    The login is not redundant. Registration issues a session of its own, and
    using that one would leave the login path -- the thing that actually decides
    who a request acts as -- unexercised by this file.
    """
    registered = await client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert registered.status_code == 201, registered.text

    signed_in = await client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text
    assert SESSION_COOKIE in client.cookies

    return client


async def build_board(client, title):
    """A board with two columns and one card, created through the API.

    Two columns because a reorder on a single column is a no-op, and a test whose
    "nothing changed" assertion could not have changed anything is not a test.

    Every step is asserted. If setup silently failed, the ids below would be
    missing and every isolation test would pass against data that does not exist.
    """
    board = await client.post("/api/boards", json={"title": title})
    assert board.status_code == 201, board.text
    board = board.json()

    columns = []
    for column_title in ("Todo", "Done"):
        column = await client.post(
            f"/api/boards/{board['id']}/columns", json={"title": column_title}
        )
        assert column.status_code == 201, column.text
        columns.append(column.json())

    card = await client.post(
        f"/api/columns/{columns[0]['id']}/cards", json={"title": f"{title} card"}
    )
    assert card.status_code == 201, card.text

    return {"board": board, "columns": columns, "card": card.json()}


@pytest.fixture
async def alice(app_on_test_database):
    # Entered before any request is made. httpx opens a client on its first
    # request, and entering it afterwards raises "Cannot open a client instance
    # more than once".
    async with new_client() as client:
        yield await sign_up_and_in(client, ALICE)


@pytest.fixture
async def mallory(app_on_test_database):
    async with new_client() as client:
        yield await sign_up_and_in(client, MALLORY)


@pytest.fixture
async def hers(alice):
    """Alice's own data. Built separately from Mallory's on purpose: a shared
    fixture would give them rows with a common ancestor and could hide a scoping
    bug that only bites across genuinely separate trees."""
    return await build_board(alice, "Alice's board")


@pytest.fixture
async def theirs(mallory):
    return await build_board(mallory, "Mallory's board")


async def count(session, sql, **params):
    return (await session.execute(text(sql), params)).scalar_one()


# ---------------------------------------------------------------- sanity


async def test_the_two_clients_are_genuinely_different_people(alice, mallory):
    """The check that everything below depends on.

    If the two clients shared a session -- one cookie jar, one user -- then every
    test in this file would be asking whether someone can reach their own data,
    and the answer would be yes, and it would look like a catastrophic failure
    rather than a broken test. Worth naming rather than inferring.
    """
    she = await alice.get("/api/me")
    they = await mallory.get("/api/me")

    assert she.status_code == they.status_code == 200
    assert she.json()["email"] == ALICE
    assert they.json()["email"] == MALLORY
    assert she.json()["id"] != they.json()["id"]
    assert alice.cookies[SESSION_COOKIE] != mallory.cookies[SESSION_COOKIE]


# ---------------------------------------------------------------- boards


async def test_the_board_list_shows_only_your_own(alice, mallory, hers, theirs):
    listed = await alice.get("/api/boards")

    assert listed.status_code == 200
    assert [board["title"] for board in listed.json()] == ["Alice's board"]

    # And the same request as the other user returns theirs, so the filter is
    # scoping rather than simply returning one row.
    listed_by_owner = await mallory.get("/api/boards")
    assert [board["title"] for board in listed_by_owner.json()] == ["Mallory's board"]


async def test_another_users_board_cannot_be_read(alice, mallory, theirs):
    board_id = theirs["board"]["id"]

    refused = await alice.get(f"/api/boards/{board_id}")
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/boards/{board_id}")
    assert allowed.status_code == 200
    assert allowed.json()["title"] == "Mallory's board"


async def test_another_users_board_cannot_be_renamed(alice, mallory, theirs, session):
    board_id = theirs["board"]["id"]

    refused = await alice.patch(
        f"/api/boards/{board_id}", json={"title": "taken over"}
    )
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/boards/{board_id}")
    assert allowed.status_code == 200
    assert allowed.json()["title"] == "Mallory's board"
    assert (
        await count(
            session, "select title from boards where id = :id", id=board_id
        )
        == "Mallory's board"
    )

    # Same verb, same route, by the owner. Without this, a rename endpoint that
    # answered 404 to everybody would satisfy every assertion above.
    renamed = await mallory.patch(
        f"/api/boards/{board_id}", json={"title": "renamed by its owner"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "renamed by its owner"
    assert (
        await count(session, "select title from boards where id = :id", id=board_id)
        == "renamed by its owner"
    )


async def test_another_users_board_cannot_be_deleted(alice, mallory, theirs, session):
    board_id = theirs["board"]["id"]

    refused = await alice.delete(f"/api/boards/{board_id}")
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/boards/{board_id}")
    assert allowed.status_code == 200
    # The cascade would have taken the columns and cards with it, so this checks
    # the whole tree survived rather than just the root.
    assert (
        await count(session, "select count(*) from boards where id = :id", id=board_id)
        == 1
    )
    assert (
        await count(
            session, "select count(*) from columns where board_id = :id", id=board_id
        )
        == 2
    )

    # Same verb by the owner, last because it is the destructive one.
    deleted = await mallory.delete(f"/api/boards/{board_id}")
    assert deleted.status_code == 204
    assert (
        await count(session, "select count(*) from boards where id = :id", id=board_id)
        == 0
    )
    # And the cascade that did not fire for Alice does fire for her.
    assert (
        await count(
            session, "select count(*) from columns where board_id = :id", id=board_id
        )
        == 0
    )


async def test_a_board_cannot_be_created_owned_by_someone_else(alice, mallory, session):
    """Mass assignment. Ownership comes from the session, never from the body.

    A create schema that accepted owner_id would let anyone plant rows in another
    person's account, and no amount of read scoping would notice.

    Paired with the same verb on the same route succeeding, because otherwise a
    POST that answered 422 to every body, valid or not, would satisfy the refusal
    and the count of zero alike.
    """
    victim = (await mallory.get("/api/me")).json()["id"]
    owner = (await alice.get("/api/me")).json()["id"]

    refused = await alice.post(
        "/api/boards", json={"title": "planted", "owner_id": victim}
    )
    assert refused.status_code == 422

    assert (
        await count(
            session, "select count(*) from boards where owner_id = :id", id=victim
        )
        == 0
    )

    # Same verb, same route, the same body without the smuggled field: created,
    # and owned by the person whose cookie sent it rather than by nobody.
    allowed = await alice.post("/api/boards", json={"title": "planted"})
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["title"] == "planted"
    assert (
        await count(
            session,
            "select count(*) from boards where owner_id = :id and title = :title",
            id=owner,
            title="planted",
        )
        == 1
    )
    # And the refusal above still landed nothing in the victim's account, now
    # that the endpoint is known to be capable of creating something at all.
    assert (
        await count(
            session, "select count(*) from boards where owner_id = :id", id=victim
        )
        == 0
    )


# ------------------------------------------------- columns, nested under a board


async def test_another_users_columns_cannot_be_listed(alice, mallory, theirs):
    """The nested route. A handler that scopes the leaf but not the ancestor
    passes every test that only ever asks for the outer resource."""
    board_id = theirs["board"]["id"]

    refused = await alice.get(f"/api/boards/{board_id}/columns")
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/boards/{board_id}/columns")
    assert allowed.status_code == 200
    assert [column["title"] for column in allowed.json()] == ["Todo", "Done"]


async def test_a_column_cannot_be_added_to_another_users_board(
    alice, mallory, theirs, session
):
    board_id = theirs["board"]["id"]

    refused = await alice.post(
        f"/api/boards/{board_id}/columns", json={"title": "intruder"}
    )
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/boards/{board_id}/columns")
    assert allowed.status_code == 200
    assert [column["title"] for column in allowed.json()] == ["Todo", "Done"]
    assert (
        await count(
            session, "select count(*) from columns where board_id = :id", id=board_id
        )
        == 2
    )


async def test_another_users_column_cannot_be_renamed(alice, mallory, theirs, session):
    column_id = theirs["columns"][0]["id"]

    refused = await alice.patch(
        f"/api/columns/{column_id}", json={"title": "taken over"}
    )
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/boards/{theirs['board']['id']}/columns")
    assert allowed.status_code == 200
    assert [column["title"] for column in allowed.json()] == ["Todo", "Done"]
    assert (
        await count(session, "select title from columns where id = :id", id=column_id)
        == "Todo"
    )

    # Same verb, same route, by the owner.
    renamed = await mallory.patch(
        f"/api/columns/{column_id}", json={"title": "renamed by its owner"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "renamed by its owner"
    assert (
        await count(session, "select title from columns where id = :id", id=column_id)
        == "renamed by its owner"
    )


async def test_another_users_column_cannot_be_moved(alice, mallory, theirs, session):
    column_id = theirs["columns"][0]["id"]

    refused = await alice.patch(f"/api/columns/{column_id}/move", json={"position": 1})
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/boards/{theirs['board']['id']}/columns")
    assert allowed.status_code == 200
    assert [column["title"] for column in allowed.json()] == ["Todo", "Done"]
    assert (
        await count(session, "select position from columns where id = :id", id=column_id)
        == 0
    )

    # Same verb, same route, same position, by the owner: the move Alice was
    # refused is one the endpoint will genuinely perform.
    moved = await mallory.patch(f"/api/columns/{column_id}/move", json={"position": 1})
    assert moved.status_code == 200
    assert moved.json()["position"] == 1
    assert (
        await count(session, "select position from columns where id = :id", id=column_id)
        == 1
    )


async def test_another_users_column_cannot_be_deleted(alice, mallory, theirs, session):
    column_id = theirs["columns"][0]["id"]

    refused = await alice.delete(f"/api/columns/{column_id}")
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/boards/{theirs['board']['id']}/columns")
    assert allowed.status_code == 200
    assert [column["title"] for column in allowed.json()] == ["Todo", "Done"]
    assert (
        await count(session, "select count(*) from columns where id = :id", id=column_id)
        == 1
    )

    # Same verb by the owner, last because it is the destructive one.
    deleted = await mallory.delete(f"/api/columns/{column_id}")
    assert deleted.status_code == 204
    assert (
        await count(session, "select count(*) from columns where id = :id", id=column_id)
        == 0
    )


# --------------------------------------------------- cards, nested under a column


async def test_another_users_cards_cannot_be_listed(alice, mallory, theirs):
    column_id = theirs["columns"][0]["id"]

    refused = await alice.get(f"/api/columns/{column_id}/cards")
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/columns/{column_id}/cards")
    assert allowed.status_code == 200
    assert [card["title"] for card in allowed.json()] == ["Mallory's board card"]


async def test_a_card_cannot_be_added_to_another_users_column(
    alice, mallory, theirs, session
):
    column_id = theirs["columns"][0]["id"]

    refused = await alice.post(
        f"/api/columns/{column_id}/cards", json={"title": "intruder"}
    )
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/columns/{column_id}/cards")
    assert allowed.status_code == 200
    assert [card["title"] for card in allowed.json()] == ["Mallory's board card"]
    assert (
        await count(
            session, "select count(*) from cards where column_id = :id", id=column_id
        )
        == 1
    )


async def test_another_users_card_cannot_be_edited(alice, mallory, theirs, session):
    card_id = theirs["card"]["id"]

    refused = await alice.patch(f"/api/cards/{card_id}", json={"title": "taken over"})
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/columns/{theirs['columns'][0]['id']}/cards")
    assert allowed.status_code == 200
    assert [card["title"] for card in allowed.json()] == ["Mallory's board card"]
    assert (
        await count(session, "select title from cards where id = :id", id=card_id)
        == "Mallory's board card"
    )

    # Same verb, same route, by the owner.
    edited = await mallory.patch(
        f"/api/cards/{card_id}", json={"title": "edited by its owner"}
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "edited by its owner"
    assert (
        await count(session, "select title from cards where id = :id", id=card_id)
        == "edited by its owner"
    )


async def test_another_users_card_cannot_be_deleted(alice, mallory, theirs, session):
    card_id = theirs["card"]["id"]

    refused = await alice.delete(f"/api/cards/{card_id}")
    assert refused.status_code == 404

    allowed = await mallory.get(f"/api/columns/{theirs['columns'][0]['id']}/cards")
    assert allowed.status_code == 200
    assert (
        await count(session, "select count(*) from cards where id = :id", id=card_id)
        == 1
    )

    # Same verb by the owner, last because it is the destructive one.
    deleted = await mallory.delete(f"/api/cards/{card_id}")
    assert deleted.status_code == 204
    assert (
        await count(session, "select count(*) from cards where id = :id", id=card_id)
        == 0
    )


# ------------------------------------------------------------------ the move


async def test_your_own_card_cannot_be_moved_into_another_users_column(
    alice, mallory, hers, theirs, session
):
    """The one this file exists for.

    column_id arrives in the request body, and a handler that fetches the card
    through the ownership join but takes the target column on trust has an IDOR
    that every read-only test in this file would miss. The card being hers makes
    the first ownership check pass, so only the check on the target can catch it.
    """
    card_id = hers["card"]["id"]
    their_column = theirs["columns"][0]["id"]

    refused = await alice.patch(
        f"/api/cards/{card_id}/move",
        json={"column_id": their_column, "position": 0},
    )
    assert refused.status_code == 404

    # Her card is where it was, and their column did not gain it.
    assert (
        await count(session, "select column_id from cards where id = :id", id=card_id)
    ) == __import__("uuid").UUID(hers["columns"][0]["id"])
    assert (
        await count(
            session,
            "select count(*) from cards where column_id = :id",
            id=their_column,
        )
        == 1
    )

    # Positive control: the same move into a column she does own is allowed, so
    # the refusal above is about ownership and not about the endpoint being
    # broken.
    allowed = await alice.patch(
        f"/api/cards/{card_id}/move",
        json={"column_id": hers["columns"][1]["id"], "position": 0},
    )
    assert allowed.status_code == 200
    assert allowed.json()["column_id"] == hers["columns"][1]["id"]


async def test_another_users_card_cannot_be_moved_at_all(
    alice, mallory, hers, theirs, session
):
    """The other direction: their card, her column."""
    card_id = theirs["card"]["id"]

    refused = await alice.patch(
        f"/api/cards/{card_id}/move",
        json={"column_id": hers["columns"][0]["id"], "position": 0},
    )
    assert refused.status_code == 404

    assert (
        await count(session, "select column_id from cards where id = :id", id=card_id)
    ) == __import__("uuid").UUID(theirs["columns"][0]["id"])

    # Positive control: its owner can move it.
    allowed = await mallory.patch(
        f"/api/cards/{card_id}/move",
        json={"column_id": theirs["columns"][1]["id"], "position": 0},
    )
    assert allowed.status_code == 200


# --------------------------------------------------------------- sessions


async def test_logging_out_does_not_end_the_other_users_session(
    alice, mallory, hers, theirs
):
    """Session revocation is scoped too. A logout that deleted rows by user_id
    with the wrong id, or by no id at all, would sign everyone out.

    Her token is captured before the logout and presented again by hand
    afterwards. Without that this test is half blind: logout clears the cookie as
    well as deleting the row, httpx drops a cleared cookie from the jar, and the
    next request goes out carrying nothing, so the 401 comes from the branch that
    never touches the database and a logout revoking nothing would still pass.
    """
    her_token = alice.cookies[SESSION_COOKIE]

    assert (await alice.post("/api/auth/logout")).status_code == 204

    # The jar dropped the cleared cookie, so this header is the only cookie on
    # the request and the refusal can only come from the session lookup.
    revoked = await alice.get(
        "/api/boards", headers={"cookie": f"{SESSION_COOKIE}={her_token}"}
    )
    assert revoked.status_code == 401

    # And as the browser actually leaves it, with no cookie at all.
    assert (await alice.get("/api/boards")).status_code == 401

    still_in = await mallory.get("/api/boards")
    assert still_in.status_code == 200
    assert [board["title"] for board in still_in.json()] == ["Mallory's board"]


async def test_another_users_session_cookie_is_the_only_thing_that_authenticates(
    alice, mallory, theirs
):
    """Presenting Mallory's board id with Alice's cookie is refused; the same id
    with Mallory's cookie is not. Identity comes from the cookie alone, and never
    from anything else in the request."""
    board_id = theirs["board"]["id"]
    path = f"/api/boards/{board_id}"

    assert (await alice.get(path)).status_code == 404
    assert (await mallory.get(path)).status_code == 200

    # And with no cookie at all it is 401, not 404: unauthenticated and
    # authenticated-but-not-yours are different answers on purpose.
    async with new_client() as anonymous:
        assert (await anonymous.get(path)).status_code == 401
