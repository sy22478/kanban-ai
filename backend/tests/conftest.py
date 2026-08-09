import asyncio

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import CSRF_HEADER, SESSION_COOKIE, settings
from app.db import get_session
from app.limiter import limiter
from app.main import app
from app.models import User
from app.security import hash_password

TEST_DATABASE = "kanban_test"

# Hashed once for the whole run rather than per fixture. Argon2 at 64 MiB costs
# about 65ms a time by design, and paying that in every test would add a second
# of pure waiting for no coverage. The tests that need hashing to be real go
# through the register endpoint instead.
PASSWORD = "correct horse battery staple"
PASSWORD_HASH = hash_password(PASSWORD)


def test_database_url() -> str:
    base, _, _development_database = settings.database_url.rpartition("/")
    return f"{base}/{TEST_DATABASE}"


async def _create_test_database() -> None:
    # CREATE DATABASE cannot run inside a transaction, hence AUTOCOMMIT.
    admin_url = settings.database_url
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        exists = await connection.scalar(
            text("select 1 from pg_database where datname = :name"),
            {"name": TEST_DATABASE},
        )
        if not exists:
            await connection.execute(text(f'create database "{TEST_DATABASE}"'))
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> None:
    """Build the test database from the real migrations.

    Deliberately not Base.metadata.create_all: that would test a schema the
    application never actually runs on. If a migration is wrong, these tests
    should be wrong in the same way.
    """
    asyncio.run(_create_test_database())

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", test_database_url())
    command.upgrade(config, "head")


@pytest.fixture
async def session():
    """A session on the test database, with the tables emptied first.

    The engine is created per test rather than once per session on purpose.
    pytest-asyncio gives each test its own event loop, and an engine outlives
    the loop its connection pool was created on, which surfaces later as
    "attached to a different loop" from somewhere unrelated.
    """
    engine = create_async_engine(test_database_url())

    async with engine.begin() as connection:
        await connection.execute(
            text(
                "truncate users, sessions, boards, columns, cards "
                "restart identity cascade"
            )
        )

    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session

    await engine.dispose()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear the per-IP counters between tests.

    slowapi's in-memory store lives for the life of the process, and every test
    here comes from the same address. Without this the suite poisons itself: the
    isolation tests register users repeatedly, cross the registration limit part
    way through the file, and start failing with 429 for a reason that has
    nothing to do with what they are testing -- and would look exactly like a
    tenant isolation bug.

    The limiter is left switched on rather than disabled, so a fault in it still
    surfaces. test_rate_limit.py exercises the limits deliberately.
    """
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
async def client(session):
    """An HTTP client against the real app, on the test database.

    **base_url is https on purpose, and it is load-bearing.** The session cookie
    is Secure, and http.cookiejar under the hood stores a Secure cookie received
    over http:// but then refuses to send it back. Over http://testserver the jar
    fills up and every following request goes out unauthenticated, so every
    endpoint answers 401. A tenant isolation test written that way would find
    user A blocked from user B's board, go green, and have proved nothing except
    that nobody was logged in. Verified directly: over http the app saw no
    cookie, over https it saw it.

    **get_session is overridden; get_current_user is not, ever.** Pointing the
    app at the test database is plumbing. Overriding get_current_user would
    replace the exact code the isolation test exists to exercise -- the cookie
    lookup, the session expiry, the ownership filters hanging off the returned
    user -- with a stub that hands back whichever user the test asked for. That
    version of the test passes identically whether the application is secure or
    completely broken.

    The CSRF header is sent by default because the front-end sends it on every
    request. Tests that check the CSRF middleware remove it deliberately.
    """
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="https://testserver",
        headers={CSRF_HEADER: "1"},
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()


async def register(client, email, password=None):
    """Register through the real endpoint and return the response.

    Real registration rather than an inserted row: it is the only way the
    password hashing, the session creation and the cookie all get exercised.
    """
    return await client.post(
        "/api/auth/register", json={"email": email, "password": password or PASSWORD}
    )


async def login(client, email, password=None):
    return await client.post(
        "/api/auth/login", json={"email": email, "password": password or PASSWORD}
    )


async def get_bearing(client, path, token):
    """GET carrying exactly this session token and nothing else.

    client.cookies.set(name, value, domain="testserver") is not enough and is
    actively misleading. httpx files a cookie it received under the domain
    "testserver.local", so setting one under "testserver" adds a second jar
    entry instead of replacing the first, and the client goes on sending the
    original. A test written that way reported that a rotated-away session was
    still valid, when the application had correctly deleted it -- a false alarm
    that reads exactly like a real one.

    Clearing the jar and setting the header outright leaves nothing to guess at.
    """
    client.cookies.clear()
    return await client.get(path, headers={"cookie": f"{SESSION_COOKIE}={token}"})


async def without_csrf(client, method, path, **kwargs):
    """Send a request with the CSRF header removed.

    httpx has no way to drop a client default header for one request --
    headers={NAME: None} is a TypeError, not a removal -- so the request is built
    with the defaults applied and the header deleted before it goes out. This is
    what a cross-site attacker's request looks like: the cookie is attached by
    the browser, the header is not there.
    """
    request = client.build_request(method, path, **kwargs)
    del request.headers[CSRF_HEADER]
    return await client.send(request)


@pytest.fixture
async def user(session) -> User:
    user = User(email="owner@example.com", password_hash=PASSWORD_HASH)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def other_user(session) -> User:
    """The second tenant.

    Named for the mallory@example.com row that used to be inserted into the
    development database by hand. Nothing in the repository ever created her, so
    a fresh clone had no second user and any check that relied on seeing her
    board disappear silently proved nothing. She lives here now instead.
    """
    user = User(email="mallory@example.com", password_hash=PASSWORD_HASH)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
