import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models import User

TEST_DATABASE = "kanban_test"


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
            text("truncate users, boards, columns, cards restart identity cascade")
        )

    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def user(session) -> User:
    user = User(email="owner@example.com")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def other_user(session) -> User:
    user = User(email="mallory@example.com")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
