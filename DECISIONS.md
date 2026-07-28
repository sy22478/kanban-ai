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
