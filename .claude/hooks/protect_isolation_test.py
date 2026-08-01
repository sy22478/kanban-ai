"""PreToolUse hook: keep the tenant isolation test out of reach.

Denies changes to backend/tests/test_tenant_isolation.py once it exists, through the file tools
(Edit, Write, NotebookEdit) and through the shell tools (Bash, PowerShell). Creating the file the
first time is allowed, and the rest of backend/tests/ is untouched.

The shell half is a default-deny: any shell command that names the file is refused unless the
verb is on a short read-only allowlist. That is deliberate. A deny-list of dangerous verbs fails
open on the one it has not heard of; an allowlist fails closed and still leaves `pytest` working.
"""

import os
import re
from pathlib import Path

import hook_io

RELATIVE = "backend/tests/test_tenant_isolation.py"
FILENAME = "test_tenant_isolation.py"

FILE_TOOLS = ("Edit", "Write", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")

# Anything that redirects, chains or substitutes makes the command too hard to reason about, so
# naming the file inside one is refused outright.
CHAINING = re.compile(r"[;&|<>`\n]|\$\(")

# Verbs that can read the file but cannot change it.
READ_ONLY = frozenset(
    [
        "pytest",
        "py.test",
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "wc",
        "diff",
        "ls",
        "dir",
        "stat",
        "grep",
        "rg",
        "findstr",
        "get-content",
        "get-item",
        "get-childitem",
        "select-string",
        "test-path",
        "resolve-path",
    ]
)

GIT_READ_ONLY = frozenset(["add", "blame", "diff", "log", "ls-files", "show", "status"])

PYTHON_NAMES = frozenset(["python", "python3", "py"])

ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

REASON_HEAD = """Denied by the protect-isolation-test hook.

{relative} is the boundary that proves user A cannot reach user B's data. Editing it is how a
failing isolation test quietly becomes a passing one, which is the specific failure CLAUDE.md
calls out: something that looks like it works because the failing path was never exercised."""

REASON_TAIL = """If the test is wrong, or the API it calls has legitimately changed, say so and ask Sonu."""


def verb_of(word):
    """The bare command name: no directory, no .exe, lowercased."""
    name = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def shell_is_read_only(command):
    """True when a command that names the test provably only reads it."""
    if CHAINING.search(command):
        return False

    words = command.split()
    # Claude Code strips leading VAR=value itself before matching permission rules; match that,
    # so `PYTHONPATH=. pytest <test>` is not refused for the wrong reason.
    while words and ASSIGNMENT.match(words[0]):
        words.pop(0)
    if not words:
        return False

    verb = verb_of(words[0])
    if verb in READ_ONLY:
        return True
    if verb == "git" and len(words) > 1 and verb_of(words[1]) in GIT_READ_ONLY:
        return True
    if verb in PYTHON_NAMES and words[1:3] == ["-m", "pytest"]:
        return True
    return False


def targets_protected_file(tool_input, protected):
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target or not isinstance(target, str):
        return False
    path = Path(target)
    if not path.is_absolute():
        path = hook_io.project_root() / path
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return os.path.normcase(str(resolved)) == os.path.normcase(str(protected))


def deny(detail):
    hook_io.emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "\n\n".join(
                    [REASON_HEAD.format(relative=RELATIVE), detail, REASON_TAIL]
                ),
            }
        }
    )


def main():
    payload = hook_io.read_payload()
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not tool or not isinstance(tool_input, dict):
        hook_io.emit()

    try:
        protected = (hook_io.project_root() / RELATIVE).resolve()
    except OSError:
        hook_io.emit()

    # First creation is allowed. Only an existing file is protected.
    if not protected.is_file():
        hook_io.emit()

    if tool in FILE_TOOLS:
        if targets_protected_file(tool_input, protected):
            deny("%s was called against that file." % tool)
        hook_io.emit()

    if tool in SHELL_TOOLS:
        command = tool_input.get("command")
        if not isinstance(command, str) or FILENAME.lower() not in command.lower():
            hook_io.emit()
        if shell_is_read_only(command):
            hook_io.emit()
        deny(
            "This was a %s command naming that file. Shell commands are refused unless they only\n"
            "read it: pytest, git add/diff/log/show/status, cat and the like, with no redirect,\n"
            "pipe or chaining. Routing an edit through sed, Set-Content, a redirect, mv or rm is\n"
            "the bypass this hook exists to stop." % tool
        )

    hook_io.emit()


main()
