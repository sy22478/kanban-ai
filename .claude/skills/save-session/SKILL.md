---
name: save-session
description: Write a verified snapshot of the current working session to session_state/SESSION_STATE.md, overwriting the previous one. Use when ending a session, handing work off, or before a context reset.
---

# Save session

Write `session_state/SESSION_STATE.md` so that a fresh session, with no memory of this one, can
pick the work up. Overwrite the file completely every time. There is one snapshot, never a pile of
them. The history lives in git and in `DECISIONS.md`.

The snapshot is committed, but it rides the next commit rather than making one of its own.

## 1. Verify the real state before writing anything

Do not write the snapshot from your memory of the conversation. Remembering what happened is not
evidence of what is true now. Run these first and write from their output:

```
git rev-parse --abbrev-ref HEAD
git status --short
git log --oneline -3
docker compose ps
```

If `docker compose ps` errors, or there is no compose file yet, record that plainly instead of
leaving the reader to guess whether the stack is up. Where the commands contradict something you
were about to write, the commands win and the snapshot says what the commands said.

## 2. Write the snapshot

Create `session_state/` if it does not exist. Write these sections in this order. Keep a section
and put "none" under it rather than dropping it, because a missing section reads as an oversight
and "none" reads as an answer.

- **Branch and HEAD** — branch name, short hash and subject line of HEAD, and whether the tree is
  clean. If it is dirty, list the changed paths from `git status --short`.
- **Current phase** — which phase of the build this is, and what finishing it means.
- **Exact next step** — if the work stopped mid-task, the specific next action: the file, the
  function, the command. Not "continue the API". Something closer to "add the tenant filter to
  `list_cards` in `app/api/cards.py`, then run the cross-user access test".
- **Blocked on** — what cannot move, and who or what it is waiting on. Name the person or the
  dependency. If nothing is blocked, say nothing is blocked.
- **Environment learnings** — the things a fresh session could not work out from the repository:
  which ports are in use and by what, which env vars must be set and where their values come from,
  toolchain quirks, anything that cost time to figure out and would cost the same time again.
  Do not repeat what `CLAUDE.md` or the README already says.
- **First commands on resume** — the two or three commands to run first, in order, each with one
  line on what a healthy result looks like.

## 3. Say what the snapshot is worth

End the file with this, or wording that means the same:

> This snapshot is a claim about the state of the project when it was written. It is not ground
> truth. It can be stale, and it can be wrong. Check it against the repository and the running
> services before relying on any line of it.

Write it plainly and in the first person. No emojis. Do not pad it. A short snapshot that is true
is worth more than a long one that is half remembered.
