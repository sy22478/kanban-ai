# Phase 2 plan

## Goal

Registration, login, sessions and per-user data isolation, with a test that proves user A cannot
reach user B's data.

## Decided before this plan, not to be re-asked

Sonu settled both security-boundary questions on 2026-08-01, with sources. They are recorded here
and belong in `DECISIONS.md`.

- **Server-side sessions in Postgres, delivered as a cookie. Not JWT.** Cookie
  `__Host-session`, `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`. Token is
  `secrets.token_urlsafe(32)`; the database stores `sha256(token)` and never the token. A single
  fast hash is right here because the token is uniform randomness, not a password. JWT loses
  because there is one service, every request already hits Postgres, there are no third-party
  consumers, and revocation would make it stateful anyway.
- **Argon2id via `pwdlib`, `PasswordHash.recommended()`, with `verify_and_update`.** Not
  `passlib`: last release 1.7.4 in October 2020, and it imports the stdlib `crypt` module removed
  in Python 3.13. **Confirmed against this container: `python -c "import sys; print(sys.version)"`
  reports `3.13.14`, so passlib is not merely stale here, it is broken.** Not bcrypt: OWASP now
  restricts it to legacy systems.

Also pre-decided and carried into the tasks below: the CSRF triple (custom header, content-type
rejection, Origin check), the hand-rolled `sessions` table with both a sliding idle timeout and an
absolute cap, session rotation on login, self-cleaning expiry inside the login transaction, and
slowapi plus per-account backoff.

### Two things I am flagging rather than re-asking

1. **`session_state/SESSION_STATE.md` contradicts the above.** Written 2026-07-29, it records the
   decision as `SameSite=Lax` and `argon2-cffi`. The instructions for this phase, dated
   2026-08-01, say `SameSite=Strict` and `pwdlib`. The later ones win and the snapshot is stale.
   Task 12 rewrites it. Nothing else in the repo depends on the old wording.
2. **`SameSite=Strict` has a visible cost and I want it on the record.** A top-level navigation
   arriving from any other site does not carry the cookie, so someone following a link into the
   app from elsewhere sees a logged-out page until they navigate within it. For a portfolio app a
   recruiter may click into, that reads as a bug. `Lax` would avoid it. Strict is the safer
   choice, the custom-header CSRF defence does not depend on it, and this app has no inbound deep
   links yet, so I am implementing Strict as instructed. Recorded so the symptom is not
   mistaken for a defect later.

## What I found before planning, that changes the work

Four things, each verified rather than assumed.

### 1. `httpx` stores a `Secure` cookie over `http://` and then never sends it

This is the trap that would make the isolation test pass for the wrong reason. Run in the backend
container against a real ASGI app:

```
http://testserver  set-cookie: __Host-session=abc; HttpOnly; Path=/; SameSite=strict; Secure
http://testserver  jar: {'__Host-session': 'abc'}
http://testserver  /me sees: {'cookie': None}
https://testserver set-cookie: __Host-session=abc; HttpOnly; Path=/; SameSite=strict; Secure
https://testserver jar: {'__Host-session': 'abc'}
https://testserver /me sees: {'cookie': 'abc'}
```

The cookie lands in the jar either way, so `assert client.cookies` passes. It is simply never
returned. A test client built on `base_url="http://test"` would run every "authenticated" request
unauthenticated, both users would get 401 on everything, and `assert status != 200` would go
green while proving nothing at all.

**Consequence: every authenticated test client uses `base_url="https://testserver"`.** The ASGI
transport does no TLS, so the scheme only satisfies the cookie jar. It also matches where phase 4
is going.

### 2. The Vite proxy rewrites `Host`, so the Origin check cannot compare against it

`frontend/vite.config.ts` sets `changeOrigin: true`. That rewrites the outgoing `Host` to
`backend:8000` while the browser's `Origin` stays `http://localhost:5173`. Validating `Origin`
against `request.headers["host"]` would reject every real request. It would also be wrong on
principle: `Host` is caller-controlled.

**Consequence: the allowed origin is explicit configuration, not derived from the request.**

### 3. `GET /api/users` returns every registered email address

`app/main.py:14`. Phase 0's plumbing check, currently unauthenticated and unscoped. Once
registration exists it is a user-enumeration endpoint. `grep` across `frontend/src` finds no
caller, so deleting it breaks nothing; `/api/me` covers the same plumbing purpose.

### 4. `mallory@example.com` exists only because she was inserted by hand

Confirmed: nothing in the repository creates her. `app/seed.py` inserts `sonu@example.com` only.
So the cross-user check that phase 1 relied on for eyeballing the UI does not survive a fresh
clone. It moves into `backend/tests/test_tenant_isolation.py`, which builds both users through
real registration. After this phase, no manual database row is load-bearing for any check.

Both hand-made rows have no password, which collides with a `NOT NULL password_hash`. That is
question 1 below.

## Questions, and the answers

Three, asked in one batch on 2026-08-01. The security-boundary ones were already decided and were
not re-asked.

1. **The two passwordless users, and their boards.** Migration 0003 adds `password_hash NOT NULL`
   to `users`; `sonu@example.com` and `mallory@example.com` cannot satisfy it.

   **Answer: Sonu deletes them by hand, and the migration stays pure schema.** No `DELETE` goes
   into a migration, so `DECISIONS.md`'s "migrations are schema history; fixtures are not schema"
   line from 2026-07-29 holds without an exception carved into it. The accepted cost is that the
   migration fails loudly on any database that still holds passwordless rows. That is a
   reproducibility footgun for anyone restoring Sonu's development volume, and it is deliberate:
   failing loudly beats a migration that quietly rewrites user rows.

   **This blocks task 2.** The exact command is in task 0 below and it is Sonu's to run, not mine.

2. **Password change and logout-everywhere: in scope or not?** The instructions say to rotate the
   session id "on login and on password change", but `CLAUDE.md` phase 2 asks for registration,
   login, sessions and isolation, and says "no feature I did not ask for".

   **Answer: both left out.** Rotation on login is built. Rotation on password change has nothing
   to attach to and is recorded as unbuilt rather than quietly dropped. Logout-everywhere stays
   one `DELETE FROM sessions WHERE user_id = $1` away, which is the property that won sessions
   over JWT; it just does not ship this phase.

3. **Registration cannot be enumeration-proof without email.** The instruction is "If that email
   address is in our database, we have sent a link", which presumes a mail channel this app does
   not have.

   **Answer: a duplicate registration returns 409 and the leak is accepted, on the record.**
   Login stays byte-identical and timing-flat, which is where an attacker works at scale, and
   slowapi blunts scripted probing of register. Choosing the alternative would mean telling
   someone their registration succeeded when it did not, in an app with no password reset, which
   is a dead end with no way out. This goes in `DECISIONS.md` as a known accepted leak whose fix
   is email verification, not as an oversight.

## Tasks

Each task states what it is authorised to touch. Anything outside that list means stopping and
re-planning, not widening the task. Each names the verification that gets run, and it is that one
rather than a similar one, per the lesson logged on 2026-08-01: **verifying one instance of a
pattern is not verifying the pattern**, so where a task covers N paths it verifies N paths.

### 0. Sonu clears the passwordless rows (blocks task 2)

Per the answer to question 1, this one is not mine to run.

```
docker compose exec db psql -U kanban -d kanban -c "delete from users;"
```

That cascades to boards, columns and cards, so the development "Kanban AI" board and Mallory's
board go with it. Everything after this is created through real registration.

**Verified by:** `select count(*) from users;` returning 0 before I touch migration 0003. I will
check it rather than take it as done.

### 1. Dependencies and settings

Add `pwdlib[argon2]` (0.3.0), `slowapi` (0.1.10) and `pydantic[email]` to `pyproject.toml`, and
the phase 2 settings: session lifetimes, cookie name, the allowed origin. No secret is added,
because opaque server-side sessions need no signing key. That is a genuine advantage of this
design over JWT and is worth stating in `DECISIONS.md`.

**Authorised scope:** `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/config.py`,
`.env.example`.

**Verified by:** rebuild the image, then in the container
`python -c "from pwdlib import PasswordHash; print(PasswordHash.recommended().hash('x'))"`, and
read the parameters out of the printed string: it must be `$argon2id$` with `m=65536,t=3,p=4`,
which is above the OWASP floor of 19 MiB / t=2 / p=1. Not "the import worked".

### 2. Migration 0003: `password_hash` and the `sessions` table

`users.password_hash text not null`, added plainly with no server default and no data statement,
which is only safe because task 0 emptied the table. New table
`sessions(id uuidv7 pk, user_id uuid fk users on delete cascade, token_hash bytea unique not null,
created_at, last_used_at, expires_at, user_agent)`, indexed on `user_id` and `expires_at`.

**Authorised scope:** `backend/alembic/versions/0003_*.py`, `backend/app/models.py`.

**Verified by:** `alembic upgrade head`, then `psql \d users` and `\d sessions` showing the
column, the unique constraint on `token_hash`, both indexes, and the `ON DELETE CASCADE`. Then a
real cascade check: insert a session for a user, delete the user, confirm
`select count(*) from sessions` returns 0. Then `alembic downgrade -1` and `upgrade head` again,
proving it is reversible the way 0001 and 0002 were.

### 3. `app/security.py`: hashing, tokens, and the dummy hash

`PasswordHash.recommended()`, a `hash_password`, a `verify_password` returning
`(ok, new_hash_or_none)` from `verify_and_update`, `new_session_token()` using
`secrets.token_urlsafe(32)`, `token_digest()` using sha256, and a module-level `DUMMY_HASH`: a
real Argon2id hash of an unguessable random string, generated once at import, used when no such
user exists so the work done is identical.

**Authorised scope:** `backend/app/security.py`, `backend/tests/test_security.py`.

**Verified by:** pytest covering each of the five, separately. Round trip; wrong password false;
verifying against `DUMMY_HASH` returns false rather than raising; two calls to
`new_session_token()` differ and decode to 32 bytes; `token_digest` is 32 bytes and stable. Plus a
timing check that the real-user and no-such-user paths are within the same order of magnitude,
since that is the property the dummy hash exists for.

### 4. `app/services/sessions.py`

Create, look up, delete one, delete all for a user, purge one user's expired rows. Lookup enforces
both expiries: `expires_at > now` (absolute, never extended) and
`last_used_at > now - 14 days` (idle). `last_used_at` is written only when it is more than a
minute stale, so a busy session is not an UPDATE per request.

**Authorised scope:** `backend/app/services/sessions.py`, `backend/tests/test_sessions.py`.

**Verified by:** pytest, one test per property, each by manipulating timestamps in the database
rather than sleeping. (a) The raw token appears nowhere: `select token_hash from sessions` and
assert the token string is not in it. (b) A session idle for 15 days is rejected. (c) A session
used one second ago but created 91 days ago is rejected, which is the one a sliding-only
implementation gets wrong. (d) Two lookups inside a minute produce one `last_used_at` write. (e)
Purge removes this user's expired rows and leaves another user's alone.

### 5. Auth endpoints, and `get_current_user` reading the session

`POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, and `GET /api/me`
becoming the signed-in check. Register returns 409 on a duplicate address per the answer to
question 3; login leaks nothing. `get_current_user` reads the cookie and returns 401 when there is no
valid session; its signature does not change, so nothing that depends on it changes. That is the
claim `plan/PHASE_1.md` made and this is where it gets tested.

Argon2 runs inside `await asyncio.to_thread(...)`, not in a sync `def` handler. The sync-handler
option in the instructions does not work here: FastAPI threadpools a sync handler, and a
threadpooled sync function cannot `await` the async SQLAlchemy session every one of these
endpoints needs. `to_thread` moves the 50ms of CPU off the loop while leaving the database work
async, which is the only combination that satisfies both.

Login: normalise the email to lowercase, look the user up, then **always** perform exactly one
Argon2 verify, against `DUMMY_HASH` when there is no such user and also when the account is in
backoff. No early return before that verify, or the fast path becomes the oracle. One generic 401,
same status, same body, whether the email is unknown, the password is wrong, or the account is
locked. Then rotate: delete any session the caller already presented, purge this user's expired
rows, insert the new session. All in one transaction.

The login and register bodies are never logged.

**Authorised scope:** `backend/app/routers/auth.py`, `backend/app/deps.py`, `backend/app/main.py`,
`backend/app/schemas.py`, `backend/app/services/users.py`.

**Verified by:** curl against the running stack, each path separately. Register, then `GET /api/me`
returning that user. Login with the wrong password, and login as an address that does not exist:
assert the two responses are byte-identical in status and body, and time both to confirm neither
is the fast one. `GET /api/boards` with no cookie returning 401. Log out, then the same request
returning 401 again. Then in psql: the `password_hash` column contains an `$argon2id$` string and
nothing resembling the password, and `sessions.token_hash` does not contain the cookie value.

### 6. CSRF middleware

On every request whose method is not GET, HEAD or OPTIONS: require the custom header, reject the
three CORS-simple content types, and check `Origin`, falling back to `Referer`, against the
configured origin. Absent `Origin` and absent `Referer` is allowed, because a browser always sends
`Origin` on a cross-site state-changing request, so absence means a non-browser client, which has
no ambient cookie to abuse. The custom header is the load-bearing control and it blocks form posts
outright, since a form cannot set one.

**Authorised scope:** `backend/app/csrf.py`, `backend/app/main.py`, `backend/tests/test_csrf.py`.

**Verified by:** a curl matrix against the running stack, every row run. Correct request succeeds.
No custom header, 403. `Content-Type: application/x-www-form-urlencoded`, 415, and the same for
`multipart/form-data` and `text/plain` — three rows, not one, per the pattern lesson.
`Origin: https://evil.example`, 403. Bad `Referer` with no `Origin`, 403. GET with none of it,
still 200. Plus an audit that no GET route mutates: list every GET handler and show it only reads.

### 7. Rate limiting

slowapi per-IP on the auth endpoints, plus per-account backoff on `users` (`failed_login_count`,
`locked_until`), reset on success. The two do different jobs: slowapi rejects before the handler
runs and is the control against the Argon2 memory DoS, since 64 MiB times concurrency is the
actual vector; the per-account counter is the control against credential stuffing from rotating
IPs, which per-IP alone cannot see.

Two things to get right. The lockout response is the same generic 401, never a 423 or 429, or the
lockout itself tells an attacker the account exists. And the test suite must not poison itself:
slowapi's in-memory store persists across tests in one process, so the isolation test registering
users repeatedly would eventually 429 and fail for an unrelated reason. `conftest.py` resets the
limiter between tests, and one dedicated test exercises the limit deliberately.

Known limitation to record, not to fix here: behind the Vite proxy `request.client.host` is the
frontend container's IP, so in development the per-IP bucket is shared by all proxied traffic.
Real per-IP limiting needs a trusted-proxy header policy, which belongs in phase 4 and is a
bypass if done carelessly.

**Authorised scope:** `backend/app/routers/auth.py`, `backend/app/services/users.py`,
`backend/app/main.py`, `backend/app/models.py`, a migration for the two columns,
`backend/tests/conftest.py`, `backend/tests/test_rate_limit.py`.

**Verified by:** a loop of failed logins against the running stack, showing 401s giving way to a
429 from slowapi. Then, with the limiter reset, a second loop showing the per-account lockout
returning a 401 that is byte-identical to a wrong-password 401. Then confirm the correct password
is also refused while locked, which is the property that makes it a lockout rather than a message.

### 8. Delete the seed path

Remove `app/seed.py`, `SEED_USER_EMAIL` from `app/config.py`, the `python -m app.seed` step from
`docker-compose.yml`, and `GET /api/users` from `app/main.py`.

**Authorised scope:** those four files.

**Verified by:** `grep -rn "seed\|SEED_USER_EMAIL" backend/ docker-compose.yml` returning nothing,
`docker compose up` starting clean with no missing-seed error, and `curl -i /api/users` returning
404.

### 9. The isolation test

`backend/tests/test_tenant_isolation.py`. This is the phase's deliverable.

**It is written after tasks 5 to 8 are hand-verified, deliberately.** The
`protect_isolation_test.py` hook denies every edit to this path once the file exists, so there is
exactly one attempt at it and a wrong line has to be taken to Sonu. What stops that ordering from
shaping the test around whatever the code happens to do is that its content is fixed here, in
advance, by the matrix below rather than by the implementation.

Both users are built by real registration and real login through `POST /api/auth/login`, carrying
the real cookie. No `app.dependency_overrides` on `get_current_user`: overriding it bypasses the
exact code under test and is indistinguishable, in a passing run, from a test that works.
`base_url="https://testserver"` for the reason proven above.

Every route, every verb, with B's real ids used by A:

| Route | Verbs |
| --- | --- |
| `/api/boards/{id}` | GET, PATCH, DELETE |
| `/api/boards/{id}/columns` | GET, POST |
| `/api/columns/{id}` | PATCH, DELETE |
| `/api/columns/{id}/move` | PATCH |
| `/api/columns/{id}/cards` | GET, POST |
| `/api/cards/{id}` | PATCH, DELETE |
| `/api/cards/{id}/move` | PATCH |

The nested routes are in the table on purpose: a handler that scopes the leaf and not the ancestor
passes a test that only ever asks for the outer resource.

Plus the move endpoint from both directions, because it takes `column_id` from the body and that
is where trust usually leaks: A moving her own card into B's column, and A moving B's card
anywhere. Plus `GET /api/boards` not listing B's board. Plus logout with B's session cookie.

Four rules, each aimed at a specific way this test could pass vacuously:

- **Positive control in the same test.** Every negative asserts A gets the exact expected refusal
  and that B gets 200 on the identical id and body. Without it, a board that was never committed
  gives both users 404 and the test proves nothing.
- **Exact status codes.** `assert response.status_code == 404`, never `!= 200`, which a 422 from a
  malformed UUID satisfies.
- **State asserted after every write attempt.** A refused PATCH or DELETE is also checked not to
  have changed B's row, because the status code alone does not prove the write did not land.
- **No shared fixture between the two users' data.** A and B are registered separately and each
  builds their own board, column and card through the API.

**Verified by:** two steps, and the second is not optional and is not done afterwards.

**9a. `pytest -q` green.**

**9b. Prove it can fail, before believing it.** A test suite that has never failed has not been
verified. `DECISIONS.md`, 2026-08-01: verifying one instance of a pattern is not verifying the
pattern. That rule applies to the test itself, so this is four separate breaks and not one.

For each, the loop is: remove the scoping, run the suite, **confirm it goes red and name which
assertion caught it**, restore the scoping, confirm green again. A break that turns the file red
by erroring during setup does not count, because that is the fixture failing rather than the
assertion catching anything.

1. **The move endpoint first**, because it is the likeliest to be trusted: `column_id` arrives in
   the request body and `cards.move_card` is the only place that decides whether the caller owns
   the column they named. Remove the `get_owned_column(session, user, target_column_id)` call and
   read the target column by id alone.
2. `get_owned_board`: drop `Board.owner_id == user.id`.
3. `get_owned_column`: drop the join to `boards`.
4. `get_owned_card`: drop the join up through `columns` to `boards`.

One break proves one filter is covered. Four breaks prove the four that exist are.

### 10. Front-end: register, log in, log out

`/login` and `/register` routes, a guard redirecting to `/login` on 401, a logout control, and the
CSRF header on every non-GET in `api.ts`. Session state comes from `GET /api/me`.

**Authorised scope:** `frontend/src/api.ts`, `frontend/src/main.tsx`,
`frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/RegisterPage.tsx`,
`frontend/src/pages/BoardListPage.tsx`, `frontend/src/pages/BoardPage.tsx`,
`frontend/src/types.ts`, `frontend/src/styles.css`.

**Verified by:** in the browser, each path clicked rather than inferred. Register a new account and
land signed in. Log out and confirm `/` redirects to `/login`. Log in again. Register a second
account, create a board on it, then sign back in as the first and confirm that board is absent
from the list and that pasting its URL gives the not-found path rather than the board. Then, in
devtools, confirm the cookie is present with `HttpOnly` and `Secure` set and that
`document.cookie` cannot see it — which is also the check that the `__Host-` prefix over
`http://localhost` was actually accepted by the browser rather than silently dropped.

### 11. Success criteria

Run every phase 2 criterion from `CLAUDE.md`, quoting output.

**Authorised scope:** no source changes. If this task needs a code change, that is a defect and it
goes back to the task that owns the file.

**Verified by:** registration and login working (task 10's browser run); passwords hashed (psql
showing `$argon2id$`); a signed-in user seeing only their own boards (task 10 and task 9); the
isolation test passing and provably able to fail (task 9); and no secret in the repo or the client
bundle — `git grep` for the password and cookie values across the tree, plus building the
front-end and grepping `dist/` for anything from `.env`.

### 12. Session state and close-out

Rewrite `session_state/SESSION_STATE.md`, including correcting the stale `SameSite=Lax` and
`argon2-cffi` lines. List the proposed `DECISIONS.md` entries for Sonu to run `/log` on. Commit
one working increment. Do not push, do not run `/log`.

**Authorised scope:** `session_state/SESSION_STATE.md`, `plan/PHASE_2.md`.

## What I am deciding without asking

Below the hour-to-undo bar. Say if you disagree.

- **Custom CSRF header is `X-Kanban-CSRF: 1`.** Not `X-Requested-With`, which has enough legacy
  baggage that people assume things about it.
- **`403` for a missing header or a bad origin, `415` for a rejected content type.** Accurate
  beats uniform when the reader is me at a terminal.
- **Password policy: minimum 12, maximum 128, no composition rules,** per OWASP. The maximum is
  not cosmetic: Argon2 over an unbounded input is a memory DoS.
- **Emails validated with `EmailStr` and stored lowercased,** so `A@x.com` and `a@x.com` cannot
  become two accounts under the unique index.
- **Registration signs you in.** One session created on success, same as login.
- **`/login` and `/register` are separate routes.** `plan/PHASE_1.md` chose react-router partly
  for this.
- **slowapi's in-memory store, not Redis.** One backend process in development. A second process
  makes it wrong, which is a phase 4 problem and gets noted there.
- **`user_agent` truncated to 512 characters** before insert, so a long header cannot fail a write.

## Out of scope, stated so it is not silently missing

Password reset, email verification, "remember me", account deletion, and any admin view. None are
in `CLAUDE.md` phase 2.

**Password change and logout-everywhere, per the answer to question 2.** Consequences worth
naming rather than leaving implicit: the instruction "rotate the session id on login and on
password change" is only half satisfied this phase, and there is no way to revoke a stolen session
other than that session logging itself out. Both become one small endpoint each whenever there is
an account settings page to reach them from.

**Registration enumeration, per the answer to question 3.** `POST /api/auth/register` tells a
caller whether an address is already registered. Accepted deliberately, not missed.
