# kanban-ai

A Kanban board with an assistant that can act on it. Boards, columns and cards,
drag and drop, multi-user with per-user isolation, and a chat that creates,
edits, moves and deletes cards on the board you have open by calling scoped
tools against the same API the UI uses.

React and TypeScript, FastAPI and Postgres, Alembic migrations, all in Docker.

## Run it

Needs Docker. Nothing else.

```
cp .env.example .env      # then set POSTGRES_PASSWORD
docker compose up
```

The app is on http://localhost:5173. Register an account and it is yours;
there is no seeded user.

The assistant needs an [OpenRouter](https://openrouter.ai) key in `.env` as
`OPENROUTER_API_KEY`. Without one the rest of the application works normally and
the assistant answers 503 saying it is not configured. The model is pinned in
`backend/app/config.py` rather than read from the environment, so changing it is
a commit somebody reviews.

## Tests

```
docker compose exec backend pytest -q
docker compose exec frontend npx tsc --noEmit
```

Three tests are skipped by default. They call the real model, so they cost money:

```
docker compose exec -e KANBAN_LIVE_AGENT_TESTS=1 backend pytest tests/test_agent_injection_live.py
```

They measure whether the model resists instructions planted in card text, which
is a property of the model rather than of this repository and so cannot be
asserted from the code. Everything that *is* a property of the code, including
the limits that hold when the model has been talked over entirely, runs in the
normal suite.

## Deploy

`docker-compose.prod.yml` builds both services for production: no bind-mounted
source, no dev dependencies, the back-end unpublished so only nginx can reach
it, and the front end built to static files that nginx serves and proxies `/api`
from. It works on any container host.

```
ALLOWED_ORIGIN=https://your.domain docker compose -f docker-compose.prod.yml up -d --build
```

Two things it will not work without:

- **HTTPS.** The session cookie is `__Host-` prefixed and `Secure`, which
  browsers enforce. Served over plain http on anything but localhost the browser
  refuses to store it and nobody can sign in. Put it behind something that
  terminates TLS.
- **`ALLOWED_ORIGIN` set to the real public origin**, scheme included, no
  trailing slash. The CSRF check compares against it and fails closed, so a
  wrong value refuses every write rather than accepting a bad one.

If you put another proxy in front of nginx, which is what most hosts do when
they terminate TLS, read the note in `frontend/nginx.conf` about which forwarded
address the rate limiter ends up counting.

## Reading it

`DECISIONS.md` is the log of what was chosen and why, including the things that
turned out to be wrong. `plan/` holds the per-phase plans. `CLAUDE.md` is the
brief the project was built to.
