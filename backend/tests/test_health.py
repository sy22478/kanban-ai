"""The health endpoint a container host probes.

Small, but the thing it is easiest to get wrong is not whether it answers 200:
it is whether it answers 200 when the instance cannot actually serve anything,
and whether it tells an unauthenticated caller more than up or down.
"""

from app.main import app


class TestHealth:
    async def test_it_answers_without_a_session(self, client):
        """A probe has no cookie. If this needed one it would report every
        healthy instance as unhealthy and no traffic would ever be routed."""
        client.cookies.clear()

        response = await client.get("/api/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_it_says_nothing_beyond_up_or_down(self, client):
        """It is unauthenticated and public, so its body is its whole exposure.

        No version, no hostname, no database name. GET /api/users was removed in
        phase 2 for being a user-enumeration endpoint that nobody had thought of
        as one; this is the same shape of risk on a new endpoint.
        """
        body = await (await client.get("/api/health")).aread()
        text = body.decode()

        assert set((await client.get("/api/health")).json()) == {"status"}
        for leak in ("postgres", "asyncpg", "kanban_test", "password", "version"):
            assert leak not in text.lower()

    async def test_it_reports_unavailable_when_the_database_is_gone(self, client):
        """The reason it touches the database at all.

        A process that is listening but cannot reach Postgres answers every real
        request with a 500. A check that only proved the process was alive would
        keep it in rotation doing exactly that.
        """
        from app.db import get_session

        class BrokenSession:
            async def execute(self, *args, **kwargs):
                raise ConnectionError("the database is not there")

        previous = app.dependency_overrides.get(get_session)
        app.dependency_overrides[get_session] = lambda: BrokenSession()
        try:
            response = await client.get("/api/health")
        finally:
            if previous is None:
                app.dependency_overrides.pop(get_session, None)
            else:
                app.dependency_overrides[get_session] = previous

        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
