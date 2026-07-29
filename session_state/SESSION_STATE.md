# Session state

Written 2026-07-28.

## Branch and HEAD

Branch `main`. HEAD is `1e7b380 Log: writes landed in sandbox, not outputs folder`.
Tree is clean; `git status --short` returned nothing.

## Current phase

Phase 0, not started. The repository is documentation only: `CLAUDE.md`, `DECISIONS.md`,
`README.md`, `.gitignore`, and `.claude/` holding the commands and skills. No application code,
no `docker-compose.yml`, no back-end, no front-end, no migrations.

Finishing phase 0 means `docker compose up` brings up Postgres, the FastAPI back-end and the
React front-end together, and the front-end displays one value that came from the database
through the API. No features beyond that. Then commit.

## Exact next step

Nothing is mid-task. The last session only appended to `DECISIONS.md` and wrote a skill outside
the repo.

Phase 0 has not been authorised to start. `CLAUDE.md` says do not start a phase until Sonu says
so, and it also says to ask questions before starting a phase rather than after. So the next
action is to ask the phase 0 questions and get the go-ahead, not to write code.

## Blocked on

Sonu, for two things:

- Permission to start phase 0.
- The exact OpenRouter model slug for phase 3. `CLAUDE.md` says to ask and not to guess, because
  a slug was picked silently on a previous project. Not needed yet, but it is an open question
  owned by him.

## Environment learnings

- **A write tool reporting success does not mean the file is on the host.** A previous session
  wrote nine documents that never reached the machine; they went to a sandbox scratchpad that
  accepted a Windows-shaped path and returned success each time. Fixed there by connecting a
  concrete directory. Before writing anything Sonu needs to open, and after writing it, read one
  file back with the host-side `Read` tool. Full procedure is in
  `C:\Users\Casey\.claude\skills\verify-writes-reach-disk\SKILL.md`, outside this repo and not
  under version control, so it will not arrive with a clone.
- **The git remote uses an SSH host alias, not `github.com`:**
  `git@github-personal:sy22478/kanban-ai.git`. It resolves through the user's SSH config.
  `git push` worked unattended on 2026-07-28. If a push fails to resolve the host, that alias is
  the first thing to look at.
- **The shell is Windows PowerShell 5.1.** `&&` and `||` are parser errors. Chain with
  `A; if ($?) { B }`.
- Docker: `docker compose ps` fails with "no configuration file provided: not found". That is
  expected, not a broken stack. There is no compose file yet; writing it is phase 0 work.

## First commands on resume

```
git -C F:\kanban-ai log --oneline -3
```
Healthy: HEAD is `1e7b380` or later on `main`. If it is behind that, this snapshot is stale.

```
git -C F:\kanban-ai status --short
```
Healthy: no output. Anything listed is uncommitted work this snapshot does not know about.

```
docker compose ps
```
Healthy right now: it errors with "no configuration file provided". Once phase 0 lands it should
instead list three running services. An error after that point means the stack is down.

---

This snapshot is a claim about the state of the project when it was written. It is not ground
truth. It can be stale, and it can be wrong. Check it against the repository and the running
services before relying on any line of it.
