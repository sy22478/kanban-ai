# Session state

Written 2026-07-29.

## Branch and HEAD

Branch `main`. HEAD is `f4a9ca9 Add run-phase skill and command`, which is pushed.

The tree is dirty: phase 1 is complete but not yet committed at the time of writing. The commit
follows immediately after this file. Changed and new paths:

```
 M backend/Dockerfile              M backend/app/models.py
 M backend/alembic/env.py          M backend/app/schemas.py
 M backend/app/config.py           M backend/pyproject.toml
 M backend/app/main.py             M backend/uv.lock
 M frontend/package.json           M frontend/package-lock.json
 M frontend/src/main.tsx           D frontend/src/App.tsx
 M session_state/SESSION_STATE.md
 ?? backend/alembic/versions/0002_create_boards_columns_cards.py
 ?? backend/app/deps.py  ?? backend/app/ordering.py
 ?? backend/app/routers/  ?? backend/app/services/  ?? backend/tests/
 ?? frontend/src/api.ts  ?? frontend/src/components/  ?? frontend/src/pages/
 ?? frontend/src/styles.css  ?? frontend/src/types.ts  ?? plan/
```

If HEAD is a phase 1 commit and the tree is clean, that commit happened and this paragraph is
stale in the harmless direction.

## Current phase

Phase 1 is functionally complete. Phase 2 has not been authorised to start.

Boards, columns and cards exist with full create, read, update, delete, move and reorder,
persisted in Postgres and usable in the browser at `localhost:5173`. `plan/PHASE_1.md` holds the
task list, the verification for each task, and the four decisions Sonu made.

The design point that carries into phase 2: `app/deps.py` has `get_current_user()`, which returns
the seeded user and is the only place that decides who the request acts as. Every board query
filters on `owner_id`; columns and cards are reached only by joining up through their board, never
by their own id. In phase 2 the body of that one function changes and nothing else should have to.

## Exact next step

Nothing is mid-task, but one thing is unverified and it is the first thing to settle.

**Mouse drag and drop is not verified.** Keyboard drag is verified end to end: focus a card grip,
Space, Right, Space produced `PATCH /api/cards/{id}/move` 200 and the row moved in Postgres with
both columns renumbered contiguously. Mouse drag was attempted three times through Chrome
automation and never produced a move:

- `left_click_drag` dispatches a single mousemove; dnd-kit's PointerSensor needs the activation
  move plus at least one further move before it has an `over` target, so `onDragEnd` saw
  `over === null` and returned.
- Synthetic `PointerEvent`s with `await` gaps did activate the drag (the DragOverlay appeared) but
  left it stuck open, and an active dnd-kit drag runs a continuous rAF loop that starved the main
  thread and timed out CDP. A page reload cleared it.
- The same events dispatched synchronously never activated at all, because dnd-kit measures
  droppable rectangles asynchronously on activation.

All three failures are consistent with driving dnd-kit through CDP rather than with a broken
application, and `onDragEnd` is shared with the verified keyboard path, so only PointerSensor
activation is in doubt. That is a belief, not a verification. **Ask Sonu to drag one card with the
mouse and say whether it worked.** If it did not, the suspects are `activationConstraint` in
`BoardPage.tsx` and the `useDroppable` target being `.cards` rather than the column element.

After that, ask the phase 2 questions and get the go-ahead. Phase 2 is the security-critical
phase: registration, login, sessions, per-user isolation, and a test proving user A cannot reach
user B's data.

## Blocked on

Sonu, for three things:

- Confirmation that mouse drag works, as above.
- Permission to start phase 2, plus its questions (session cookies versus JWT, and the password
  hashing library, are both on the security boundary so neither is mine to pick).
- The exact OpenRouter model slug for phase 3. `CLAUDE.md` says ask, do not guess. Not needed yet.

## Environment learnings

Phase 0's learnings still hold: ports 5173, 8000 and 5432; `.env` required and not in the repo;
Postgres 18 mounts at `/var/lib/postgresql`; venv at `/opt/venv`; Vite polls for changes;
PowerShell 5.1 has no `&&`; remotes use the `github-personal` SSH alias.

New in phase 1:

- **Rebuilding the frontend image does not update its `node_modules`.** The anonymous volume on
  `/app/node_modules` survives `docker compose build` and `up`, so new dependencies are missing
  inside the container while `package.json` looks correct. The symptom is TypeScript reporting
  "Cannot find module" for a package that is plainly installed. Fix:
  `docker compose up -d --force-recreate --renew-anon-volumes frontend`.
- **`pytest` needs `pythonpath = ["."]`.** pytest puts the test file's own directory on `sys.path`,
  not the project root, so `import app` fails from `tests/` without it.
- **Alembic's `env.py` now respects a url the caller already set.** That is what lets the test
  suite point the real migrations at `kanban_test` instead of the development database.
- **The test database is `kanban_test`,** created automatically by `tests/conftest.py` and built by
  running the real migrations rather than `create_all`, so a wrong migration makes the tests wrong
  in the same way instead of hiding it.
- **Create the async engine per test, not per session.** pytest-asyncio gives each test its own
  event loop, and an engine outliving the loop its pool was created on fails later with a
  "different loop" error from somewhere unrelated.
- **Relationships use `lazy="raise"`.** Under async SQLAlchemy an accidental lazy load surfaces as
  `MissingGreenlet` somewhere unrelated; this turns it into an immediate error at the access site.
  Callers must use `selectinload`, as `get_owned_board(..., with_contents=True)` does.
- **The position unique constraints are `DEFERRABLE INITIALLY DEFERRED`,** because renumbering
  necessarily passes through states where two rows share a position. Verified directly in psql.
- **Chrome automation: click by element `ref`, not by screenshot coordinates,** and expect
  intermittent `Page.captureScreenshot` timeouts that succeed on a retry. `window.innerWidth` is
  1568 and matches the screenshot, so coordinates are not scaled; the early failures were the
  renderer being briefly unresponsive.
- **The development database contains a second user, `mallory@example.com`, with one board.** It
  was inserted by hand to test cross-user access and is deliberately left in place: it makes the
  scoping visible in the UI, since that board never appears. Do not be surprised by it, and do not
  seed it in code.

## First commands on resume

```
git -C F:\kanban-ai log --oneline -3
```
Healthy: HEAD is the phase 1 commit, or `f4a9ca9` with a dirty tree matching the list above.

```
docker compose ps
```
Healthy: three services up, `db` marked healthy. If down, `docker compose up -d`, which needs
`.env`.

```
docker compose exec -T backend pytest -q
```
Healthy: 19 passed. This covers the ordering invariants and the ownership scoping.

```
curl -s http://localhost:5173/api/boards
```
Healthy: a JSON array containing the "Kanban AI" board and never Mallory's. A 500 means Postgres
is unreachable, which is intended rather than a fallback.

---

This snapshot is a claim about the state of the project when it was written. It is not ground
truth. It can be stale, and it can be wrong. Check it against the repository and the running
services before relying on any line of it.
