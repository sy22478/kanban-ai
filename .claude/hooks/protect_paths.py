"""PreToolUse hook: keep this repository's protected files out of reach.

The protected set is read from .claude/protected_paths.txt, one repo-relative path or glob per
line, blank lines and lines starting with # ignored. A missing file means protect nothing, so the
mechanism is present and inert rather than absent.

Denies changes to those files once they exist, through the file tools (Edit, Write, NotebookEdit)
and through the shell tools (Bash, PowerShell). Creating a file the first time is allowed: only an
existing file is protected, which is also why a glob that matches nothing yet costs nothing.

The shell half is a default-deny: any shell command that names a protected file is refused unless
the verb is on a short read-only allowlist. That is deliberate. A deny-list of dangerous verbs
fails open on the one it has not heard of; an allowlist fails closed and still leaves `pytest`
working.
"""

import os
import re
from pathlib import Path

import hook_io

PATHS_RELATIVE = ".claude/protected_paths.txt"

FILE_TOOLS = ("Edit", "Write", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")

GLOB_CHARS = re.compile(r"[*?\[]")

# Anything that redirects, chains or substitutes makes the command too hard to reason about, so
# naming a protected file inside one is refused outright.
CHAINING = re.compile(r"[;&|<>`\n]|\$\(")

# Verbs that can read a file but cannot change it.
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

REASON_HEAD = """Denied by the protected-paths hook.

{relative} is listed in {paths_file}. Those files are the ones whose quiet weakening would be this
repository's silent failure: the check stops proving what it claims while still reporting green.
Editing one is how that happens."""

REASON_TAIL = """If the file is genuinely wrong, or the thing it pins has legitimately changed, say so and ask Sonu.
Remove it from {paths_file} deliberately rather than working around this hook."""


def load_patterns(root):
    """The lines of protected_paths.txt, comments and blanks dropped. Missing file means none."""
    try:
        text = (root / PATHS_RELATIVE).read_text(encoding="utf-8")
    except OSError:
        return []
    patterns = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line.replace("\\", "/"))
    return patterns


def resolve_protected(root, patterns):
    """Every existing file the patterns name, as {resolved absolute path: repo-relative pattern}.

    Only existing files are returned. Creating a protected path the first time stays allowed, and
    a glob matching nothing yet is simply inert until something matches it.
    """
    protected = {}
    for pattern in patterns:
        if GLOB_CHARS.search(pattern):
            try:
                matches = root.glob(pattern)
            except (OSError, ValueError, IndexError):
                continue
        else:
            matches = [root / pattern]
        for match in matches:
            try:
                if not match.is_file():
                    continue
                resolved = match.resolve()
            except OSError:
                continue
            protected[os.path.normcase(str(resolved))] = pattern
    return protected


def verb_of(word):
    """The bare command name: no directory, no .exe, lowercased."""
    name = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def shell_is_read_only(command):
    """True when a command that names a protected file provably only reads it."""
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


def file_tool_target(root, tool_input, protected):
    """The protected path a file tool is aimed at, or None."""
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target or not isinstance(target, str):
        return None
    path = Path(target)
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve()
    except OSError:
        return None
    return protected.get(os.path.normcase(str(resolved)))


def shell_names_protected(command, protected):
    """The protected path a shell command names, by basename, or None.

    Matching on the basename over-blocks a same-named file elsewhere in the tree. That is the
    fail-closed direction, and the message says which file triggered it.
    """
    lowered = command.lower()
    for key in protected:
        name = Path(key).name
        if name and name.lower() in lowered:
            return protected[key]
    return None


def deny(relative, detail):
    hook_io.emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "\n\n".join(
                    [
                        REASON_HEAD.format(relative=relative, paths_file=PATHS_RELATIVE),
                        detail,
                        REASON_TAIL.format(paths_file=PATHS_RELATIVE),
                    ]
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

    root = hook_io.project_root()
    patterns = load_patterns(root)
    if not patterns:
        hook_io.emit()

    protected = resolve_protected(root, patterns)
    if not protected:
        hook_io.emit()

    if tool in FILE_TOOLS:
        relative = file_tool_target(root, tool_input, protected)
        if relative:
            deny(relative, "%s was called against that file." % tool)
        hook_io.emit()

    if tool in SHELL_TOOLS:
        command = tool_input.get("command")
        if not isinstance(command, str):
            hook_io.emit()
        relative = shell_names_protected(command, protected)
        if not relative:
            hook_io.emit()
        if shell_is_read_only(command):
            hook_io.emit()
        deny(
            relative,
            "This was a %s command naming that file. Shell commands are refused unless they only\n"
            "read it: pytest, git add/diff/log/show/status, cat and the like, with no redirect,\n"
            "pipe or chaining. Routing an edit through sed, Set-Content, a redirect, mv or rm is\n"
            "the bypass this hook exists to stop." % tool,
        )

    hook_io.emit()


main()
