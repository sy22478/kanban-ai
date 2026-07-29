---
name: run-phase
description: Run a build phase end to end with human checkpoints. Decomposes the phase into tasks, works them one at a time, stops to ask when a decision is the human's to make, and commits a working increment. Use when the user says "run phase N", "start phase N", "continue the phase", or asks to build the next phase.
---

# Run phase

Take a phase from `CLAUDE.md` from "not started" to "committed and working", without needing to be
told what to do next at every step, and without making decisions that are not yours to make.

The point is not autonomy. The point is that the human is asked **fewer times, about better
things**.

## 0. Before anything

1. Read `CLAUDE.md`. It defines the phases, the constraints, and what done means. It wins over
   anything in this file.
2. Read `session_state/SESSION_STATE.md` if it exists, then **verify its claims** against
   `git status --short` and `git log --oneline -3`. It is a claim, not ground truth.
3. Read `DECISIONS.md`. A question already settled there must not be asked again.
4. Confirm the phase before this one is actually complete and committed. If it is not, say so and
   stop.
5. `CLAUDE.md` says do not start a phase until told. If the user has not clearly said to start
   this phase, ask and stop.

## 1. Plan, and get the plan approved

Write `plan/PHASE_<n>.md`:

- The phase goal in one sentence, taken from `CLAUDE.md`.
- A numbered task list. Each task is one commit-sized piece of work, small enough that its
  verification is obvious.
- For each task: **how it will be verified**. A command, a test, an observation. Not "it works".
- A list of the questions you already know you must ask, so the human sees them up front rather
  than being interrupted five times.

Then **stop and present the plan.** Do not begin work until the human approves it. This is the
highest-leverage checkpoint in the whole skill: a bad plan wastes an entire phase, and it is
cheaper to fix here than anywhere downstream.

## 2. Ask everything you can in one batch

Use the interactive question form. Batch the questions rather than dribbling them out. For each,
give a **recommended option** and one line on why. The human should be able to accept your
recommendations without reading further, and disagree cheaply when they want to.

### Stop and ask when

These are not judgment calls. If one applies, stop.

- **A third-party service, API, or library is being chosen.** Not the version of something
  already decided. The choice itself.
- **A schema decision that is expensive to reverse.** Primary key types, relationships, anything
  that becomes painful once rows exist.
- **Anything touching the security boundary.** Auth, sessions, tenant isolation, secrets,
  anything in `CLAUDE.md`'s security section.
- **The spec is ambiguous.** `CLAUDE.md` does not decide it and a reasonable person could go
  either way.
- **Money will be spent**, or an external account is required.
- **The action is irreversible.** Force push, dropping data, deleting a migration that has run
  somewhere, deploying.
- **You are about to contradict `CLAUDE.md` or `DECISIONS.md`.** Say so plainly and explain why;
  do not quietly deviate.

### Do not ask about

Asking about these is worse than deciding. It trains the human to stop reading the questions.

- Naming: files, variables, functions, routes.
- File and folder layout inside an established pattern.
- Library versions, where the library is already chosen.
- Anything `CLAUDE.md` or `DECISIONS.md` already decides. Follow it.
- Formatting, style, comments.
- Anything you can verify in under a minute by reading the code.

If unsure: would a wrong answer here cost more than an hour to undo? If no, decide it and say
what you decided in the phase report.

## 3. Work the tasks

One task at a time, in order.

For each task:

1. Do the work.
2. **Run the verification you wrote in the plan.** Not a similar check. The one you specified.
3. If it fails, find the root cause before changing anything. `CLAUDE.md` forbids guessing and
   band-aids. A fix you cannot explain is not a fix.
4. Record anything learned that a future session would otherwise rediscover. Do not stop to
   write skills mid-phase; collect them for step 5.

Rules while working:

- **Never claim something works without exercising the path that would fail.** A feature that
  renders correctly and a feature that is hardcoded look identical from outside.
- Push token-heavy work into subagents: reading large files, searching broadly, running verbose
  test suites. Keep the main context for the work itself.
- If context gets tight mid-phase, run `/save-session`, then tell the human to `/clear` and
  invoke this skill again. Do not try to continue in a degraded context.

## 4. Stop early when you should

Stop and report, rather than pushing on, when:

- A stop-and-ask trigger fires and there is no answer yet.
- The same verification fails twice for different reasons. That means the plan is wrong, not the
  code.
- You are about to do something the plan does not cover. Re-plan and re-approve instead.
- Something in the repository contradicts something else and you cannot tell which is current.

Stopping with a clear question is a good outcome. Guessing is not.

## 5. Close the phase

1. Run the phase's success criteria from `CLAUDE.md`. All of them. Quote the actual output.
2. Run `/save-session`.
3. For anything learned that meets `capture-skill`'s bar, run `capture-skill`. Skills earn their
   place by being the second time you did something.
4. Commit **one working increment** for the phase, per `CLAUDE.md`. Body explains what and why,
   not a file list.
5. Do **not** push, and do **not** run `/log`. Both are the human's call. List the entries you
   believe belong in `DECISIONS.md` and let them run `/log` themselves.

## 6. Report

Keep it short. The human has been away.

- What the phase now does, and the evidence. Actual command output, not a summary of it.
- The negative test: what you did to prove it is not faking success.
- Decisions you made without asking, and why they were below the bar.
- Anything you could not verify, marked plainly as unverified.
- Suggested `DECISIONS.md` entries with their tags.
- What is next.

## Rules

- No emojis, anywhere.
- Never invent a verification result. If you did not run it, say you did not run it.
- Uncertainty stated plainly beats confidence that turns out to be wrong. This project has been
  bitten repeatedly by tools reporting success while doing nothing.
- The phase is not done because you say it is. It is done because its success criteria ran and
  passed in front of you.
