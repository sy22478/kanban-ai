"""The per-IP rate limiter.

Its own module so the auth router can decorate handlers with it without importing
app.main, which imports the auth router.

**In development the per-IP bucket is shared, and that is not fixed.** Behind the
Vite dev proxy every request reaches the back-end from the front-end container,
so request.client.host is one address for all proxied traffic. It does not matter
there: the only client is the developer.

**In production it is handled, in two halves that only work together.** nginx
replaces X-Forwarded-For with the address it actually saw, discarding whatever
the client sent, and uvicorn is run with --proxy-headers so that
request.client.host becomes that value. Either half alone is wrong: without
nginx overwriting it a client sets the header itself and evades the limit by
varying one string, and without --proxy-headers the header is ignored and every
client shares nginx's address again. See frontend/nginx.conf and
docker-compose.prod.yml, which carry the other halves of this comment.

The remaining gap, recorded because it is real: if another proxy sits in front of
nginx, which is what a container host terminating TLS does, then the address
nginx sees is that proxy's and every client shares a bucket again. Fixing that
needs the hop count for the specific host, which is a deployment fact rather than
a code one. nginx.conf says where to change it.

In-memory storage, not Redis, so the counts are per process. That is why
docker-compose.prod.yml runs exactly one worker: a second would keep its own
counters and every limit would silently become twice as loose. Scaling out means
giving the limiter shared storage first.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
