---
name: capture-skill
description: Turn a just-solved problem into a reusable skill so a future session does not rediscover it. Use when the user says "capture this", "make this a skill", "remember how to do this", or after solving something that took real effort to work out.
disable-model-invocation: true
---

# Capture Skill

Write what was just learned into a reusable skill. This is how the project accumulates
capability instead of re-solving the same problems.

## When this is worth doing

Capture when ALL of these hold:
- The solution took more than one attempt, or the correct order of steps was not obvious.
- It will plausibly come up again in this project.
- It is not already written down in CLAUDE.md or an existing skill.

Do NOT capture: one-line fixes, anything already in the docs, general knowledge that is not
specific to this project, or a procedure you have not actually run successfully. A skill
describing something that was never verified is worse than no skill.

## Steps

1. **Name it for the trigger, not the topic.** The description is what makes it fire, so write
   it as when to use this. Include the words a person would actually type.

2. **Write the procedure, not the story.** Numbered steps someone can follow cold. Include the
   exact commands, paths, and flags. Omit the narrative of how it was discovered.

3. **Record the trap.** If there is a wrong path that looks right, say so explicitly and say
   why it fails. This is usually the most valuable line in the file.

4. **Note what verifies it.** The command or observation that proves the procedure worked.
   Without this, the skill can rot silently as the codebase changes.

5. **Write it** to `.claude/skills/<kebab-name>/SKILL.md`, then tell the user the path and a
   two-line summary. Do not commit unless asked.

## Rules

- One skill, one job. If it needs "and" in the name, it is two skills.
- Cite real file paths from this repo, never invented ones.
- If a step was not actually run and confirmed, mark it UNVERIFIED rather than stating it
  plainly.
- No emojis.
