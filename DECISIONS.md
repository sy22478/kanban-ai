# Decisions

This is a public running log of the decisions I made building this project, the options I turned
down, the bugs I hit, and the things that surprised me. It is written as I go and pushed as I go.
It is not reconstructed at the end, and it is not tidied up afterwards: entries are appended in
chronological order and existing entries are never edited, including the ones that turned out to
be wrong. A wrong decision left visible next to what it cost is the point of keeping the log.

Every entry carries exactly one tag:

- **DECISION** — a choice I made and am now working from.
- **REJECTED** — an option I considered and turned down, and why it lost.
- **BUG** — something that broke, its root cause, and the fix. Not just the symptom.
- **SURPRISE** — behaviour that did not match what I expected, and what I believe now instead.

---

## 2026-07-27

### DECISION — **Claude Code only, no Cursor or Codex, for every project in this course.**

### DECISION — **Built from scratch and multi-user with auth, against advice to inherit a front-end and ship single-user first.**
The advice was to start from an existing front-end and add auth later. I chose the larger build
because I want to learn full-stack and auth properly rather than reach a demo quickly. I am
accepting the extra scope and a real security surface as the price of that.

### DECISION — **Spec written by hand before any code.**
The schema is multi-user from phase 1, so adding auth is wiring rather than a rewrite.
Tenant isolation will be tested with an actual cross-user access attempt, not assumed to hold
because the queries look correct.

### SURPRISE — **Every document written tonight went to a sandbox scratchpad, not my machine.**
The session had no connected folder, so the writes never reached the outputs folder. The tool
accepted a Windows path and reported success the entire time. Fixed by mounting F:\claude-docs
directly.

---

## 2026-07-29

### BUG — **Postgres 18 refuses to start on the pre-18 volume mount point.**
The first `docker compose up` had the db container exit 1. Postgres 18 keeps its data in a
major-version subdirectory under `/var/lib/postgresql`, and refuses to start when it finds data at
the old `/var/lib/postgresql/data`, which it reports as an unused mount. I had written the pre-18
`pgdata:/var/lib/postgresql/data`; the fix was to mount at `/var/lib/postgresql` and recreate the
volume. The error text talks about `pg_upgrade` and reads like corrupted data, which tempts you to
delete the volume and retry instead of moving the mount point.

### DECISION — **UUID primary keys, not integers, and uuidv7 rather than uuidv4.**
IDs go into URLs from phase 1 onward, and changing a primary key type once boards and cards exist
is a painful migration. Cheap now, expensive later.
Unguessable IDs are defence in depth only. Query-layer scoping in phase 2 is the actual control;
treating opaque IDs as the control would just be an IDOR that is inconvenient to exploit.
uuidv7 over uuidv4 because Postgres 18 ships it natively, so it costs no extension, and it is
time-ordered: inserts append to the end of the B-tree index instead of scattering through it and
fragmenting it as the table grows.

### DECISION — **The development seed user lives in `app/seed.py`, not in migration 0001.**
Migrations run in every environment, so a development row written into 0001 would arrive in
production when phase 4 deploys. Migration history is schema; fixtures are not schema.
The script is idempotent (`insert ... on conflict do nothing`) so restarts do not duplicate the
row, and it gets deleted in phase 2 when real registration replaces it.

---

## 2026-08-01

### SURPRISE — **Phase 1 was declared complete with the add-column UI never once clicked.**
Testing the board by hand on 30 July, I clicked "Add column" and nothing happened. Phase 1 had been
committed and pushed as finished five days earlier.

`plan/PHASE_1.md` task 3 verified the column endpoints by curl. Task 7, "Front-end: create, rename,
delete", covers boards, columns and cards, and its stated verification was "create a card in the
browser, then psql showing that exact row". That verification was run, and it passed. It exercises
one of the three things the task claims. The add-column path was never clicked before the phase was
called done, and the plan's own wording made that look like full coverage.

The plan says at the top of the task list: "The verification is the one that gets run, not a
similar one." I followed that rule for each individual task and still missed this, because the gap
was not between the planned check and the run check. It was inside a single planned check that
named three things and tested one.

What I believe now: **verifying one instance of a pattern is not verifying the pattern.** A task
covering N similar paths needs N verifications, or it needs splitting into N tasks. "Structurally
identical to the card path, which works" is a hypothesis about code, not evidence about behaviour,
and this is exactly the failure `CLAUDE.md` was written to prevent — in the phase built to avoid
it. Curl proving the endpoint and the browser proving one sibling of the UI does not add up to the
UI working.

The same lesson applied to fixing it: the silent no-op reported on the add-column form was also in
the add-card form and in the inline rename, and three more inputs could reach the same 422. All of
them were fixed, not just the one that was noticed.

### BUG — **Every failed write on the board page was invisible, at two independent points.**
Clicking "Add column" produced nothing. The back-end had returned 422 twice and named the failing
field; the browser showed no error at all. Two separate defects, either of which alone would have
hidden it:

- `api.ts` threw `POST /boards/... failed with 422` and discarded `response.detail`, so the
  server's explanation was destroyed at the client boundary. This affected every endpoint, and made
  the comment sitting directly above it ("Surfaced to the user rather than swallowed") false in the
  one place it mattered.
- `BoardPage.tsx` had two writers of the same `error` state. A failed write set the message, then
  the refetch that followed it succeeded and called `setError(null)`. The real message rendered for
  a single frame and the final state was `null`. Proven by stubbing the POST to 500 and watching
  the state settle back to null.

Root cause of the second one: `refresh()` owned error state it had no business owning. The fix is
that it does not touch `error` at all. A single `run()` clears the error when an action starts,
refetches either way, and writes the outcome once at the end. One owner, so there is nothing left
to race.

One detail worth keeping: when the back-end is stopped, the write *and* the refetch both fail. The
action's error deliberately wins, because "POST /columns failed" names what the user was trying to
do, while "GET /board failed" describes a symptom. Reporting the refetch's error there would have
made the failure harder to read, not easier.

The 422 itself was a 201-character title, reproduced against the running back-end after the fix
made it diagnosable. `maxLength={200}` on the four inputs now agrees with the schema's cap, so that
particular 422 is no longer reachable from the UI.

### DECISION — **Column reorder shipped as header arrows, not as dragging.**
`PATCH /api/columns/{id}/move` existed and was covered by the ordering tests, but no `moveColumn`
in `api.ts` meant it was unreachable from the UI, so phase 1's "move and reorder" was not honestly
met.

Arrows over drag-and-drop. Making columns draggable meant reworking the card drag layer: the
column's droppable id collides with a sortable on the same element, `onDragEnd` would have to
disambiguate card drags from column drags, and the header would need a grip. That is a rewrite of
the one part of the board that was verified by hand and that automation provably cannot re-verify —
dnd-kit's pointer path needs a human. Arrows are a click, so they are verifiable end to end without
me, they are keyboard reachable for free, and they hit exactly the same endpoint a drag would have.
The cost is that reordering columns is less slick than reordering cards. Accepted.

### DECISION — **Positions are contiguous integers 0..n-1, with the unique constraints deferred.**
Every parent numbers its children 0..n-1, no gaps and no duplicates, and a move renumbers the
affected rows inside one transaction. The invariant is the point: a broken move fails a test rather
than merely looking odd on screen.
`(board_id, position)` and `(column_id, position)` are unique but `DEFERRABLE INITIALLY DEFERRED`,
because renumbering necessarily passes through states where two rows briefly share a position. The
constraint is checked once at commit, on the final arrangement.
Logged 2026-08-01. The phase 1 draft was not kept, so this is reconstructed from `app/ordering.py`
and migration 0002 rather than written at the time.

### DECISION — **`get_current_user()` is the only place that decides who a request acts as.**
In phase 1 it returns the seeded user. In phase 2 its body reads the session instead and nothing
that depends on it has to change, which is the whole reason it exists this early.
Ownership is structural rather than a check bolted on afterwards: `owner_id` is part of the board
query itself, and columns and cards are reached by joining up through their board, never by their
own id alone. A board the current user does not own returns 404 and not 403, because 403 confirms
the row exists and belongs to someone else.
Logged 2026-08-01, reconstructed from `app/deps.py`, `app/services/boards.py` and
`plan/PHASE_1.md`. The phase 1 draft was not kept.

### DECISION — **Request logic lives in `app/services`, with the routers kept thin.**
A route handler declares its path, its request schema and its status code, then delegates.
The ownership lookups, the position renumbering and every write sit in `app/services`.
The reason is phase 3. The agent's tools have to go through the same validated logic the UI already
uses, and if that logic lived in the route handlers the agent would need its own copy of it. That is
exactly how a second, less-guarded path gets built by accident.
Logged 2026-08-01, reconstructed from the `app/routers` and `app/services` split and `CLAUDE.md`'s
rule that the agent gets no separate path. The phase 1 draft was not kept.

### SURPRISE — **Rebuilding a Docker image does not refresh an anonymous volume.**
I added a front-end dependency, rebuilt the image, and TypeScript still reported "Cannot find
module" for a package plainly listed in `package.json`. I had expected a rebuild to be enough.
The anonymous volume on `/app/node_modules`, which exists so the Windows bind mount does not hide
the image's Linux-built modules, survives both `docker compose build` and `up`. The container kept
serving the old modules while the new ones sat unused in the fresh image. What updates it is
`docker compose up -d --force-recreate --renew-anon-volumes frontend`.
Logged 2026-08-01 from the note I made at the time in `session_state/SESSION_STATE.md`, so the
detail here is contemporaneous even though the entry is late.

### BUG — **A running claude process served a `settings.json` it had never loaded.**
For a whole session the hook protecting `backend/tests/test_tenant_isolation.py` never fired, nor
did the SessionStart hook, nor the deny rules on `.env` and force pushes, while every freshly
started process loaded the identical file correctly: the hooks menu read 0 configured there and 3
here. Root cause of the inert state is unconfirmed, either the approval state on changed hooks or a
process predating the config, but the rule holds either way: after any change under `.claude/`,
exit and restart `claude`, then confirm the count in the hooks menu before trusting the guard.

### SURPRISE — **`git apply` writes the protected isolation test without any command naming it.**
I expected the PreToolUse guard to cover the shell as well as the file tools, and for a command
line it does, because it matches on the path appearing in the command. A patch carries the path
inside its own body, so `git apply` edits the file while the command mentions only the patch.
Nothing is fixed yet and the hole is real; the guard stops reflex and typos, not intent.

## 2026-08-07

### SURPRISE. **settings.json carries 36 deny rules, not the 39 every document claimed.**
The count came out of the new generated session banner on its first run. Three documents, the
scaffold prompt and the knowledge base all said 39, all copying each other rather than the file.
Nothing was broken, but the number was the evidence people were citing for the guard being real,
and it was wrong. This is the argument for generating the banner instead of restating it.

### DECISION. **The guardrails are now config driven, so they can be copied to the other repos.**
protect_isolation_test.py is protect_paths.py, reading .claude/protected_paths.txt. session_start.py
counts the deny rules, names the hooks per event, and reports how many protected paths match a real
file, all read at session start. The CLAUDE.md lift takes its heading names from
.claude/session_start_sections.md, defaulting to Security, because the other six repos name their
boundary section HIPAA rules, Safety invariants, Non-negotiables or Privacy boundaries.

### SURPRISE. **A stale zero byte .git/index.lock had been blocking every commit here since 5 August.**
No git process was running and the file was two days old. The same lock existed in all six target
repos and in EverAfter and landing-page, the three SEPA ones written within seven seconds of each
other, which points at an interrupted batch sweep rather than a crash in normal use. Reads worked
throughout, so nothing looked wrong until a write was attempted.
