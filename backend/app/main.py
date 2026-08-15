from fastapi import APIRouter, FastAPI, status
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.csrf import csrf_guard
from app.deps import CurrentUser, SessionDep
from app.limiter import limiter
from app.models import User
from app.routers import agent, auth, boards, cards, columns
from app.schemas import UserRead

app = FastAPI(title="Kanban AI")

# Deliberately no CORSMiddleware. The Vite dev proxy means the browser only ever
# talks to one origin, so there is no cross-origin request to permit. Adding CORS
# with allow_credentials and a permissive origin regex would hand an attacker's
# page the ability to make credentialed calls, which is the hole the CSRF checks
# above are built to close.
app.middleware("http")(csrf_guard)

# slowapi reads the limiter off app.state, and answers 429 when a limit is hit.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

api = APIRouter(prefix="/api")


# GET /api/users was here from phase 0 as the walking skeleton's end-to-end
# check. It listed every row in the users table, unauthenticated, which was
# harmless when the only row was a seeded fixture and became a user-enumeration
# endpoint the moment registration existed. /api/me proves the same plumbing
# through the same layers and answers only about the caller.


@api.get("/health")
async def health(session: SessionDep):
    """Whether this instance can serve requests, for a host's probe.

    It touches the database on purpose. A process that is listening but cannot
    reach Postgres answers every real request with a 500, and a health check
    that only proves the process is alive would keep routing traffic to it.

    Unauthenticated, because a probe has no session, and it says nothing beyond
    up or down: no version, no hostname, no connection string. A 503 rather
    than an exception, so the answer is the same shape either way.
    """
    try:
        await session.execute(text("select 1"))
    except Exception:
        return JSONResponse(
            {"status": "unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return {"status": "ok"}


@api.get("/me", response_model=UserRead)
async def read_current_user(user: CurrentUser) -> User:
    """Who the request is acting as, or 401.

    This is what the front-end asks to decide whether it is signed in, rather
    than reading the cookie, which it cannot: the cookie is HttpOnly and is
    invisible to JavaScript by design.
    """
    return user


app.include_router(api)
app.include_router(auth.router)
app.include_router(boards.router)
app.include_router(columns.router)
app.include_router(cards.router)
app.include_router(agent.router)
