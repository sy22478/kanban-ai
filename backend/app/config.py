from datetime import timedelta

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


settings = Settings()
