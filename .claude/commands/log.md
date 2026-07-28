---
description: Append a tagged entry to DECISIONS.md, then commit and push it
argument-hint: DECISION|REJECTED|BUG|SURPRISE what happened
---

Append one entry to `DECISIONS.md` describing what follows, then commit and push it.

Input: $ARGUMENTS

## Choose the tag

Exactly one tag, from `DECISION`, `REJECTED`, `BUG`, `SURPRISE`. Never two. If the input genuinely
covers two things, ask which one to log rather than writing both entries.

- `DECISION` — a choice now being worked from.
- `REJECTED` — an option considered and turned down. Say why it lost.
- `BUG` — something that broke. State the root cause and the fix, not only the symptom.
  "Another user's cards appeared on the board" is the symptom; the entry has to say what allowed
  it and what changed so it cannot happen again.
- `SURPRISE` — behaviour that did not match expectation. Say what was expected, what happened,
  and what is believed now.

## Write the entry

```
### TAG — **One-line summary, ending in a full stop.**
Detail line.
Detail line.
```

- The summary is one line, bold, and says the thing itself rather than announcing that a thing was
  decided.
- At most three lines of detail. Fewer is better. None is fine when the summary already says it.
- First person, plain. Write it the way you would say it to a colleague.
- No marketing tone. No "successfully", "robust", "seamless", "leverage". No emojis.
- Use only what the input gives you. If the input is thin, the entry is short. Do not invent
  reasoning that was not stated.

## Where it goes

`DECISIONS.md` is append-only.

- If the last `##` heading in the file is today's date, append the entry at the end of the file
  under that heading.
- Otherwise append a new `## YYYY-MM-DD` heading for today at the end of the file, then the entry
  under it.

Do not edit, reword, retag, reorder, or reflow any existing entry, and do not touch anything below
the insertion point, because nothing is below it. The only change to the file is the new lines at
the end.

## Publish it

The log is only a public log if it is pushed. After appending:

```
git add DECISIONS.md
git commit -m "Log: short summary in a few words" DECISIONS.md
git push
```

Commit `DECISIONS.md` on its own. If other files are already staged, leave them staged and commit
this path only. If the push is rejected, say so plainly and stop. Do not force it.
