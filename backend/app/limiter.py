"""The per-IP rate limiter.

Its own module so the auth router can decorate handlers with it without importing
app.main, which imports the auth router.

Known limitation, recorded rather than fixed: behind the Vite dev proxy every
request reaches the back-end from the front-end container, so request.client.host
is one address for all proxied traffic and the per-IP bucket is effectively
shared. Real per-IP limiting needs a trusted-proxy policy for X-Forwarded-For,
and trusting that header without one is itself the bypass, since a client can
simply send it. That belongs with the deployment work in phase 4.

In-memory storage, not Redis. One back-end process in development. A second
process would each keep their own counts, which is a phase 4 problem too.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
