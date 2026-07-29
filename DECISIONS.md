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
