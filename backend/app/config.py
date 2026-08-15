from datetime import timedelta

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The __Host- prefix forbids a Domain attribute and requires Secure and Path=/,
# so a sibling subdomain cannot forge or overwrite this cookie. The browser
# enforces it: a cookie named this way that breaks any of those rules is dropped
# rather than stored.
SESSION_COOKIE = "__Host-session"

# Both expiries, per OWASP. The absolute cap is set at login and never extended,
# so a stolen session dies on a fixed date no matter how much it is used. The
# idle window slides on last_used_at.
SESSION_ABSOLUTE_LIFETIME = timedelta(days=90)
SESSION_IDLE_LIFETIME = timedelta(days=14)

# last_used_at is only rewritten once it is this stale, so a busy session is not
# an UPDATE on every request. The cost is that idle expiry is accurate to within
# this window, which at 14 days does not matter.
SESSION_TOUCH_INTERVAL = timedelta(minutes=1)

# Requests that change state must carry this header. A cross-site form cannot set
# one, and a cross-site fetch that tries is stopped by the preflight it triggers.
CSRF_HEADER = "X-Kanban-CSRF"

# Per-account login backoff. Free attempts first, so somebody mistyping their own
# password a few times is not locked out, then doubling delays.
LOGIN_FREE_ATTEMPTS = 5
LOGIN_BACKOFF_CAP = timedelta(minutes=15)

# Per-IP limits, enforced by slowapi before the handler runs. This is the control
# against the Argon2 memory denial of service rather than against guessing: 64 MiB
# times the number of concurrent login attempts is the actual vector, and the
# per-account counter cannot help because it only acts after the hash is computed.
LOGIN_RATE_LIMIT = "10/minute"
REGISTER_RATE_LIMIT = "20/hour"

# The agent. Sonu chose this slug on 2026-08-12 and confirmed it live on
# OpenRouter as supporting tool calling. CLAUDE.md is explicit: do not substitute
# another one, ask. It is pinned here rather than read from the environment so
# that changing it is a commit somebody reviews.
OPENROUTER_MODEL = "deepseek/deepseek-v4-flash-0731"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# How many model round trips one chat turn may take. A turn that needs more than
# this is looping, and the request is answered rather than left to run up cost.
AGENT_MAX_STEPS = 6
AGENT_TIMEOUT_SECONDS = 60.0

# The mechanical half of the prompt-injection defence: what one turn is allowed
# to do, regardless of what the model decided. These hold when the model has been
# fully talked over, which is the case the system prompt cannot cover.
#
# The numbers are a deliberate trade. CLAUDE.md's own example request is "add
# three cards for the login flow", so the ceiling has to sit well above that or
# ordinary use hits it. Deletions get their own, much lower bound because bulk
# creation is common and recoverable while bulk deletion is neither, and
# "delete every card" is the canonical payload.
#
# This bounds the blast radius rather than preventing the first bad call. A
# budget that allowed none of either would also refuse the user's own requests,
# and an agent that cannot act is not the goal.
AGENT_MAX_MUTATIONS = 10
AGENT_MAX_DELETIONS = 3

# Unlike the login limits, this one is about spend as much as abuse: every call
# past it is real money at a third party.
AGENT_RATE_LIMIT = "20/minute"

# Only these are safe to accept on a state-changing request. They are the three
# content types a form can send without a CORS preflight, which is exactly what
# makes them the bypass.
FORBIDDEN_CONTENT_TYPES = (
    "application/x-www-form-urlencoded",
    "multipart/form-data",
    "text/plain",
)


class Settings(BaseSettings):
    """Application settings, read from the environment.

    There is no default for database_url on purpose. If it is missing the process
    fails at import time rather than quietly falling back to something local.

    allowed_origin does have a default, and that is not the same mistake: a wrong
    value rejects writes rather than accepting them, so it fails closed. It comes
    from configuration rather than from the request's Host header because the Vite
    proxy sets changeOrigin, which rewrites Host to backend:8000 while the browser
    still sends Origin: http://localhost:5173. Host is also caller-controlled, so
    it was never the right thing to compare against.
    """

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    allowed_origin: str = "http://localhost:5173"
    # Optional, and the default is None rather than a raise, because the
    # application has to boot without it: the whole app minus the agent is what
    # phases 0 to 2 built, and the test suite never calls a real model. The
    # endpoint answers 503 when it is missing, which fails closed and says so,
    # rather than the process dying at import for everyone.
    #
    # It is never sent to the browser. The frontend compose service is given no
    # environment at all, so there is no path from here into the bundle.
    openrouter_api_key: str | None = None

    @field_validator("openrouter_api_key")
    @classmethod
    def _blank_key_is_no_key(cls, value: str | None) -> str | None:
        """An unset compose variable arrives as "", not as absent.

        docker-compose passes OPENROUTER_API_KEY: ${OPENROUTER_API_KEY:-}, so a
        developer who has not set one gets an empty string here rather than
        nothing. Without this the "is it configured" check passes, the 503 never
        fires, and the first symptom is a 401 from OpenRouter dressed up as a
        502. Normalising at the boundary means one definition of "missing".
        """
        return value or None


settings = Settings()
