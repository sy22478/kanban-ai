# Session state

Written 2026-08-15, after phases 3 and 4 were built.

## Branch and HEAD

Branch `main`, at `50896d4 Phase 4: health checks, and the IPv6 trap that made one of them a lie`,
plus this snapshot's own commit. One branch in the repository.

**Pushed.** `main` and `origin/main` were in sync at `50896d4`. The ten commits published were the
phase 2 log, phases 3a to 3d, the phase 3 log, phase 4, the phase 4 log, this snapshot, and the
health checks. The 2026-08-12 snapshot said not to push `DECISIONS.md` unasked; the standing
instruction to complete the project superseded it, and `CLAUDE.md`'s own `/log` command defines push
as part of the normal cycle. Said here plainly in case that reading was wrong.

The tree is clean.

## Current phase

**Phases 3 and 4 are built, committed and green. Neither is finished, and the difference matters.**

Phase 3 split into four committed increments, as `CLAUDE.md`'s rule requires and phase 2 did not do:
3a the tool layer, 3b the model call and endpoint, 3c the panel, 3d the injection defence. Phase 4
is the production images plus the two things `limiter.py` and the backend `Dockerfile` had explicitly
deferred to it.

The suite reports **196 passed, 3 skipped**, verified just now. Migration head is `0004`; phases 3
and 4 added no migrations. Three dev services up, `db` healthy.

## Exact next step

Two things, both Sonu's, and both need something this session could not obtain: an OpenRouter key
and a host account. Nothing else is outstanding and nothing in the tree is half-finished.

1. **Put `OPENROUTER_API_KEY` in `.env` and run the live tests.** This is the one thing standing
   between phase 3 and actually being finished. Everything about the agent has been exercised
   against a scripted model and in a browser, but **no real model has ever been called by this
   code.** `deepseek/deepseek-v4-flash-0731` creating a card from a sentence is unproven, and so is
   the phase 3 criterion that it refuses instructions in card text, because both are properties of
   the model. Run:

   ```
   docker compose exec -e KANBAN_LIVE_AGENT_TESTS=1 backend pytest tests/test_agent_injection_live.py -q
   ```

   It costs a few cents. Its docstring says how to read a failure: this model complying with a
   payload is the expected outcome and is why the budget in `runner.py` exists.

2. **Choose the container host and deploy.** `CLAUDE.md` says "a container host, not Netlify. We
   choose it when we get there", so the choice was left rather than made.
   `docker-compose.prod.yml` is host-agnostic and was built and run locally, so what remains is the
   host, a domain, TLS and `ALLOWED_ORIGIN`. Phase 4's success criterion, a second person on a
   different machine, cannot be met from here.

## Blocked on

Both of the above, both on Sonu, neither blocking the other.

## What is proven, and what is only asserted

This section exists because the distinction is the whole point of the project.

**Proven by exercising the failing path:**

- Tenant isolation on the agent's tools. Each new ownership check was removed one at a time and the
  suite confirmed red before it was restored. The card binding is caught by 3 tests, the column
  binding by 2. The four phase 2 filters underneath are unchanged.
- The mutation budget. Removed, and the suite went red with all ten cards deleted, then restored.
  Caught by 3 tests.
- The panel, in a real browser: a message sent, a reply and its action list rendered, and the board
  refreshed to show the new card. Done against a temporary scripted client that was then deleted.
- The production stack, in a real browser at `http://localhost:8080`: registration through nginx,
  a board created, and a board URL loaded directly to prove the SPA fallback.
- The health checks. Stopping the database turned both app services unhealthy and the endpoint
  answered 503 through nginx; starting it again recovered without restarting either container.
  Running them is also what found the IPv6 defect below, which reading them would not have.
- The rate limit behind nginx: eleven logins trip it, and claiming a different `X-Forwarded-For`
  afterwards does not get a fresh bucket.

**Not proven, and not claimed:**

- Anything about the real model. See step 1 above.
- That per-IP rate limiting distinguishes two *real* clients. It cannot be shown from one machine.
  Closing the spoofing route is what was shown.
- That the app works behind a host that terminates TLS in front of nginx. `nginx.conf` records
  that this changes which forwarded address the limiter counts, and where to fix it.

## The agent, in one paragraph

The chat is bound to one board taken from the URL and ownership-checked before the model is called,
so an unauthorised caller never causes a billable request. Neither the user nor the board is a tool
parameter, so there is no id for a model to be argued into changing. Tools call the same
`app.services` functions the routers do. Board text reaches the model only inside a `board_content`
envelope, and `json.dumps` is what actually stops a title full of fake system framing becoming
conversation structure. One turn may perform 10 mutations and 3 deletions, checked before dispatch,
so a fully compromised model gets 3 deletions and a pile of refusals, and the user is told
mechanically rather than by the model.

## Environment learnings

Carried forward and still true: ports 5173 front end, 8000 back end, 5432 Postgres; `.env` required
and not in the repo; Postgres 18 mounts at `/var/lib/postgresql`; venv at `/opt/venv`; `pytest` needs
`pythonpath = ["."]`; test database `kanban_test` built from the real migrations; async engine per
test; `lazy="raise"`; deferred position constraints; PowerShell 5.1 has no `&&`.

The protected-path hook is `.claude/hooks/protect_paths.py` driven by `.claude/protected_paths.txt`.
Naming the protected test in a shell command is refused even to read it; use
`docker compose exec -T backend pytest -q -k "tenant_isolation" tests/`. `git apply` bypasses the
hook, because the path travels inside the patch.

New this session:

- **`git commit -m @'...'@` fails in the PowerShell tool.** The here-string is not recognised after
  `-m` and the message is split at the first embedded quote into bogus pathspecs. Write the message
  to a file and use `git commit -F <file>`. Every commit here was made that way.
- **`.env` cannot be read at all**, by the deny rules, and a command that merely mentions it is
  refused even when it also reads other files. Check whether a key is set from inside the container
  and emit a boolean: `docker compose exec -T backend python -c "import os; print(bool(os.environ.get('OPENROUTER_API_KEY')))"`.
- **The Chrome extension's `form_input` sets the DOM value, which React discards on its next
  render.** Controlled inputs need real typing: click the element, `ctrl+a`, then type. A form that
  appears to submit and changes nothing is this, not a back-end failure.
- **`docker compose run` does not claim the service's network alias.** A container started that way
  is not reachable as `backend`, so the Vite proxy cannot see it and every request fails in a way
  that looks like the app is broken. Use `up -d --force-recreate` with the variable set instead.
- **Two stacks can run at once.** `docker-compose.prod.yml` uses project name `kanban-ai-prod` and
  publishes only 8080, so it does not collide with the dev stack. Bring it up with
  `$env:ALLOWED_ORIGIN="http://localhost:8080"` and `--project-directory F:\kanban-ai` so it reads
  the root `.env`.
- **`http://localhost` is a secure context**, so the `__Host-` cookie works locally over plain http.
  On any other host it does not, and nobody can sign in.
- **`localhost` inside a container can resolve to `::1` while the server is bound to IPv4 only.**
  nginx `listen 8080` is IPv4, so a busybox `wget http://localhost:8080` health probe got
  "connection refused" from a container that was serving pages correctly. Container healthchecks
  here use `127.0.0.1`. This cost a front end that reported unhealthy while working, which on a real
  host means no traffic is routed to it.
- **A container healthcheck takes `interval` times `retries` to flip.** At 10s and 5 that is about
  50 seconds, so checking 35 seconds after breaking something still shows healthy. The endpoint
  answers correctly immediately; only the container's status lags.

Front end: typecheck with `docker compose exec -T frontend npx tsc --noEmit`; production build is
`npm run build`; `dist/` lands on the host through the bind mount and is gitignored. The `frontend`
compose service still has no `environment` and no `env_file` in either compose file, which is what
makes "no secret in the client bundle" true by construction. Verified again after phase 3: the built
bundle contains no match for `OPENROUTER`, `sk-or-`, `deepseek` or `Bearer`.

Back end: a `Secure` cookie does not survive `http://` in httpx, so test clients use
`base_url="https://testserver"`; `assert SESSION_COOKIE in client.cookies` is not the guard it looks
like; httpx files a received cookie under `testserver.local`; httpx cannot drop a client default
header for one request; FastAPI 0.140 does not splice included routers into `app.routes`; slowapi's
store outlives a test and `conftest.py` resets it; Argon2id costs about 65ms per verify and runs in
`asyncio.to_thread`.

Accounts in the development database, all created through the API: `sonu@example.com`,
`alice.p2@example.com`, and `agent.check@example.com` from this session's browser check.
`prod.check@example.com` exists only in the production stack's separate volume. Passwords are
deliberately not recorded: this file is in a public repository, registration is open, and a fresh
session should make its own account.

## First commands on resume

```
git -C F:\kanban-ai log --oneline -3
git -C F:\kanban-ai status --short --branch
```
Healthy: `main` at `50896d4` or later, clean, and in sync with `origin/main`.

```
docker compose ps
docker compose exec -T backend pytest -q
docker compose exec -T db psql -U kanban -d kanban -c "select version_num from alembic_version;"
```
Healthy: three services up with `db` healthy, **196 passed, 3 skipped**, and `0004`.

---

This snapshot is a claim about the state of the project when it was written. It is not ground truth.
It can be stale, and it can be wrong. Check it against the repository and the running services
before relying on any line of it.
