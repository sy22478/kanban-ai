# Phase 1 plan

## Goal

Boards, columns and cards, with create, read, update, delete, move and reorder, persisted in
Postgres and usable in the browser, for one seeded user with no login yet.

## The thing that makes phase 2 wiring rather than a rewrite

Phase 1 has no auth, so there is nothing to enforce. That is exactly how a rewrite gets set up: if
phase 1 writes unscoped queries, phase 2 has to revisit every one of them.

So from the first endpoint, ownership is structural:

- `app/deps.py` gets `get_current_user()`. In phase 1 it returns the seeded user. It is the only
  place that knows how the current user is determined.
- Every board query filters on `owner_id`. Columns and cards are reached only by joining through
  their board, never by their own id alone.
- Fetching a board by id that the current user does not own returns 404, not 403. A 403 confirms
  the row exists.

In phase 2 the body of `get_current_user()` changes from "the seeded user" to "the session's
user", and nothing else has to. That is the claim this phase is making, and phase 2 is where it
gets tested rather than asserted.

## Tasks

Each task lists how it is verified. The verification is the one that gets run, not a similar one.

### 1. Migration 0002: boards, columns, cards

`boards(id, owner_id -> users.id, title, created_at)`,
`columns(id, board_id -> boards.id, title, position, created_at)`,
`cards(id, column_id -> columns.id, title, description, position, created_at)`.
uuidv7 primary keys per `DECISIONS.md`. `ON DELETE CASCADE` down the chain. Unique constraint on
`(board_id, position)` and `(column_id, position)`, deferrable so a reorder can shuffle rows inside
one transaction without tripping it mid-statement.

**Verified by:** `alembic upgrade head` succeeds, then `psql \d+ boards columns cards` shows the
foreign keys and constraints. Then a deliberate cascade test: insert a board with a column and a
card, delete the board, and confirm `select count(*) from cards` returns 0. Then `alembic
downgrade -1` and `upgrade head` again, to prove the migration is reversible.

### 2. Board endpoints, scoped through `get_current_user`

`GET /api/boards`, `POST /api/boards`, `GET /api/boards/{id}`, `PATCH /api/boards/{id}`,
`DELETE /api/boards/{id}`. Pydantic request models, no coercion of malformed input.

**Verified by:** curl each verb, checking status codes and the response body. Then the scoping
check that actually matters: insert a second user and a board owned by them directly in psql, then
`GET /api/boards/{that_id}` as the seeded user and confirm 404 rather than the board. This is the
phase 1 version of the cross-user test, run without auth existing.

### 3. Column endpoints

Nested under a board: `GET/POST /api/boards/{board_id}/columns`, `PATCH/DELETE
/api/columns/{id}`. Position assigned server side on create, appended to the end.

**Verified by:** curl create three columns, confirm positions are 0, 1, 2 in psql. Delete the
middle one, confirm the remaining positions are renumbered contiguously and not left as 0, 2.

### 4. Card endpoints and the move endpoint

`GET/POST /api/columns/{column_id}/cards`, `PATCH/DELETE /api/cards/{id}`, plus the move endpoint
whose shape is question 4 below.

**Verified by:** curl a card from column A position 0 to column B position 1. Then psql: confirm
the card's `column_id` changed, that column B's positions are contiguous 0..n with the card at 1,
and that column A closed its gap. A move that leaves a gap or a duplicate position is a failure
even if the API returned 200.

### 5. Ordering invariants under pytest

A small pytest suite against a real Postgres, exercising the ordering logic directly: move within
a column, move across columns, move to first, move to last, delete from the middle. Each asserts
positions remain contiguous with no duplicates.

This is my judgment call rather than something `CLAUDE.md` asks for in phase 1. Ordering bugs are
silent, and phase 2's tenant isolation test needs this harness to exist anyway. Cut it if you
would rather it waited.

**Verified by:** `pytest` runs green, and one assertion is deliberately inverted first to confirm
the suite can actually fail.

### 6. Front-end: read the board

API client module, board list, and a board view rendering columns with their cards.

**Verified by:** browser at `localhost:5173` showing a board created via curl in task 2, so the
data provably came from Postgres rather than front-end state.

### 7. Front-end: create, rename, delete

Boards, columns and cards, from the UI.

**Verified by:** create a card in the browser, then `psql select * from cards` showing that exact
row. Not a screenshot of the UI, which would look the same if it were local state.

### 8. Front-end: drag and drop

Wired to the move endpoint, with an optimistic local update so the board does not feel laggy, and
a refetch on error so a failed move cannot leave the UI lying.

**Verified by:** drag a card across columns in the browser, then psql confirming the new
`column_id` and contiguous positions. Then reload the page and confirm the card is where it was
dropped.

### 9. Success criteria and persistence

Run every phase 1 criterion from `CLAUDE.md`.

**Verified by:** `docker compose down` then `docker compose up -d`, then confirm the boards,
columns and cards created during this phase are all still present and correctly ordered. Plus the
negative test: stop Postgres, confirm the board view surfaces the failure rather than showing a
stale or empty board that looks like success.

## What I am deciding without asking

Below the bar of an hour to undo, so I am not spending a question on them. Say if you disagree.

- Table `columns`, model class `BoardColumn`. `Column` as a class name would shadow SQLAlchemy's
  own `Column` in the same file.
- Cards get a nullable `description` alongside `title`. One nullable column now, and phase 3's
  `edit_card` tool is thin without it.
- Deleting a board cascades to its columns and cards, in the database rather than in application
  code.
- Position numbering is server side and zero-based. Clients never send absolute positions except
  as a move target.
- No starter board in `seed.py`. It still seeds only the user, which keeps task 6's verification
  honest, since anything on screen must have been created through the API.

## Questions, and the answers

Asked in one batch on 2026-07-29. All four recommendations were accepted.

1. **Ordering: contiguous integers.** Positions are exactly `0..n-1` per parent, with no gaps and
   no duplicates. A move renumbers the affected rows in one transaction. The invariant is the
   point: a broken move is caught by a test rather than merely looking odd.
2. **Drag and drop: dnd-kit.** React 19 and StrictMode clean, keyboard and screen reader support
   included.
3. **Routing: react-router.** Real URLs per board now, and phase 2 needs `/login`, `/register`
   and a redirect guard, so the alternative is retrofitting a router onto a finished board.
4. **Move API: one endpoint.** `PATCH /api/cards/{id}/move` with `{column_id, position}`,
   describing the finished gesture in one transaction, the same call whether or not the card
   changed column. Maps one to one onto phase 3's `move_card` tool.

Task 5, the pytest suite, was not cut, so it stays in scope.
