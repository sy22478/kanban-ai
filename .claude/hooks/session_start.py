"""SessionStart hook: re-assert the security constraints at the top of every session.

Includes source "compact", which is the only documented way to get this context back after
compaction has thrown it away.
"""

import re
import subprocess

import hook_io

LIMIT = 9500

FALLBACK_SECURITY = (
    "CLAUDE.md could not be read at session start. Treat every auth, tenancy and secrets "
    "decision as non-negotiable, and ask before deviating."
)

GUARDRAILS = """Structural guardrails now in force. Do not rely on prose alone to stop you:
- Real .env files are deny-listed for Read and Edit in .claude/settings.json. .env.example stays
  readable on purpose. Denies also cover cat, head, tail and sed in a shell, but not a script that
  opens the file itself.
- Force pushes are deny-listed in every form the glob can reach, including the refspec form
  `git push origin +main` and a trailing `--force`. Deny rules are a speed bump against reflex,
  not a boundary: `git -C`, an alias or a script still gets through.
- backend/tests/test_tenant_isolation.py is write-protected by a PreToolUse hook once it exists,
  through the file tools and through the shell. A shell command naming that file is refused
  unless it only reads it. Weakening that test so it passes is the exact failure being prevented.
  If it genuinely needs to change, ask Sonu.
- Every compaction, manual or automatic, copies the raw transcript to .claude/transcripts/ first.
  That directory is gitignored: transcripts are plaintext and can contain anything a tool printed.
- A build phase starts only when Sonu says so. run-phase, save-session and capture-skill are
  invoke-only and will not self-trigger."""


def git(root, *args):
    try:
        result = subprocess.run(
            ["git", "-C", str(root)] + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", "replace").strip()


def security_section(root):
    """The Security section of CLAUDE.md, lifted verbatim so this cannot drift from the spec."""
    claude_md = root / "CLAUDE.md"
    try:
        lines = claude_md.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    start = -1
    for index, line in enumerate(lines):
        if re.match(r"^##\s+Security", line):
            start = index
            break
    if start < 0:
        return ""

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^##\s", lines[index]):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def main():
    root = hook_io.project_root()

    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    head = git(root, "log", "-1", "--format=%h %s") or "unknown"
    status = git(root, "status", "--short")
    tree = "dirty\n" + status if status else "clean"

    context = """Re-asserted at session start, including after compaction. These are constraints, not suggestions.

Live repository state, read just now rather than remembered:
- branch: {branch}
- HEAD: {head}
- working tree: {tree}

Verbatim from CLAUDE.md:

{security}

{guardrails}""".format(
        branch=branch,
        head=head,
        tree=tree,
        security=security_section(root) or FALLBACK_SECURITY,
        guardrails=GUARDRAILS,
    )

    if len(context) > LIMIT:
        context = context[:LIMIT] + "\n[truncated at %d characters]" % LIMIT

    hook_io.emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }
    )


main()
