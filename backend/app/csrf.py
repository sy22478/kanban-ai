"""Cross-site request forgery defence for a JSON API.

The threat: the session cookie is attached by the browser to any request to this
origin, including one triggered by a page on an attacker's site. SameSite=Strict
already blocks that, but OWASP is explicit that SameSite "is useful as a defense
in depth control but it does not replace a proper CSRF defense", so it is not
relied on alone here.

Three checks, on every request that changes state. They are layered because each
one closes a hole the others leave:

1. **A custom header must be present.** This is the load-bearing one, and it is
   the defence OWASP recommends for exactly this case: an API with no HTML forms.
   A cross-site <form> cannot set a header at all. A cross-site fetch that sets
   one turns the request into a CORS preflight, and with no CORS middleware in
   this application there is nothing to answer that preflight, so the browser
   never sends the real request.

2. **Form content types are refused.** application/x-www-form-urlencoded,
   multipart/form-data and text/plain are the three a form can send without a
   preflight. They are the specific bypass this check exists for: without it, an
   attacker's form posts JSON-shaped text as text/plain and a lenient parser
   accepts it.

3. **Origin, falling back to Referer, must be ours.** Defence in depth behind the
   header check.

Absent Origin *and* absent Referer is allowed. A browser always sends Origin on a
cross-site state-changing request, so absence means a non-browser client -- curl,
the test suite -- which has no ambient cookie for an attacker to abuse in the
first place. The header requirement still applies to it.

There is no secret and no token generation here, so this is not hand-rolled
crypto. It is a set of conditions on request metadata.
"""

from urllib.parse import urlsplit

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.config import CSRF_HEADER, FORBIDDEN_CONTENT_TYPES, settings

# GET, HEAD and OPTIONS are exempt because none of them may change anything. That
# is a constraint on every route in this application, not an assumption about
# them: a GET that mutates would be reachable from an <img> tag on any site in
# the world. It carries into phase 3 -- no agent tool may mutate on a GET.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _refuse(status_code: int, detail: str) -> JSONResponse:
    # The same {"detail": ...} shape FastAPI's own errors use, so the front-end
    # reads the reason instead of showing a bare status code.
    return JSONResponse({"detail": detail}, status_code=status_code)


def origin_of(url: str) -> str | None:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


async def csrf_guard(request: Request, call_next):
    if request.method in SAFE_METHODS:
        return await call_next(request)

    if CSRF_HEADER not in request.headers:
        return _refuse(
            status.HTTP_403_FORBIDDEN,
            f"This request needs the {CSRF_HEADER} header",
        )

    content_type = request.headers.get("content-type", "")
    # Split on ";" so "text/plain; charset=utf-8" is caught as text/plain.
    media_type = content_type.split(";")[0].strip().lower()
    if media_type in FORBIDDEN_CONTENT_TYPES:
        return _refuse(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"{media_type} is not accepted on this API",
        )

    # Origin is authoritative when present. Referer is the fallback, and only the
    # fallback: it is absent under some referrer policies, which is why it cannot
    # be the primary check.
    stated = request.headers.get("origin") or request.headers.get("referer")
    if stated is not None and origin_of(stated) != settings.allowed_origin:
        return _refuse(status.HTTP_403_FORBIDDEN, "Cross-origin request refused")

    return await call_next(request)
