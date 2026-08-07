"""SessionStart hook: re-assert this repository's constraints at the top of every session.

Includes source "compact", which is the only documented way to get this context back after
compaction has thrown it away.

The guardrail banner is generated from the configuration that is actually in force, never restated
by hand, so it cannot drift from reality. Three inputs, all optional:

- .claude/settings.json         deny rules and hook registrations, counted and named as found
- .claude/protected_paths.txt   the protected set, counted and matched against the working tree
- .claude/session_start_notes.md  whatever else this repository wants said at every session start

The verbatim lift out of CLAUDE.md takes its heading names from .claude/session_start_sections.md,
one heading per line, defaulting to Security. Repositories name their boundary section differently
(HIPAA rules, Safety invariants, Non-negotiables, Privacy boundaries) and a hardcoded "Security"
would silently lift nothing in most of them.
"""

import json
import re
import subprocess

import hook_io

LIMIT = 9500

SETTINGS_RELATIVE = ".claude/settings.json"
PATHS_RELATIVE = ".claude/protected_paths.txt"
NOTES_RELATIVE = ".claude/session_start_notes.md"
SECTIONS_RELATIVE = ".claude/session_start_sections.md"

DEFAULT_SECTIONS = ["Security"]

FALLBACK_SECURITY = (
    "CLAUDE.md could not be read at session start, or it has no section this repository declared "
    "as its boundary. Treat every auth, tenancy, privacy and secrets decision as non-negotiable, "
    "and ask before deviating."
)

# Labels for what a deny rule covers, matched against the rule text itself so the banner reports
# what is in settings.json rather than what someone remembers putting there.
DENY_SUBJECTS = [
    ("real .env files", re.compile(r"\.env", re.I)),
    ("force pushes", re.compile(r"push.*(--force|-f\b|\+)", re.I)),
    ("hard resets", re.compile(r"reset\s+--hard", re.I)),
    ("history rewrites", re.compile(r"filter-repo", re.I)),
    ("docker volume destruction", re.compile(r"docker.*down.*(-v\b|--volume)", re.I)),
]

CAVEAT = """Deny rules and the protected-paths hook are a speed bump against reflex, not a security boundary.
`git -C`, an alias, or a script that opens the file itself still gets through, and `git apply`
writes a protected file without the command ever naming it, because the path travels inside the
patch. That last one is demonstrated, not theoretical. Do not read any of this as making the
repository safe."""


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


def read_lines(root, relative):
    """Non-empty, non-comment lines of a config file. Missing file means an empty list."""
    try:
        text = (root / relative).read_text(encoding="utf-8")
    except OSError:
        return []
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


def sections_wanted(root):
    return read_lines(root, SECTIONS_RELATIVE) or DEFAULT_SECTIONS


def claude_md_sections(root, wanted):
    """The named sections of CLAUDE.md, lifted verbatim so this cannot drift from the spec.

    A wanted name matches any heading that starts with it, so "HIPAA rules" finds
    "## HIPAA rules (non-negotiable)".
    """
    try:
        lines = (root / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    heads = [(index, line) for index, line in enumerate(lines) if re.match(r"^#{2,}\s", line)]

    blocks = []
    for name in wanted:
        pattern = re.compile(r"^(#{2,})\s+" + re.escape(name), re.I)
        for position, (index, line) in enumerate(heads):
            match = pattern.match(line)
            if not match:
                continue
            depth = len(match.group(1))
            end = len(lines)
            # The section ends at the next heading of the same depth or shallower, so a section
            # written with ### subsections keeps them.
            for next_index, next_line in heads[position + 1:]:
                next_depth = len(re.match(r"^(#{2,})", next_line).group(1))
                if next_depth <= depth:
                    end = next_index
                    break
            blocks.append("\n".join(lines[index:end]).strip())
            break
    return "\n\n".join(block for block in blocks if block)


def settings_report(root):
    """What settings.json actually configures, counted from the file."""
    try:
        settings = json.loads((root / SETTINGS_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["- %s could not be read, so no deny rule or hook is confirmed to be in force." % SETTINGS_RELATIVE]
    if not isinstance(settings, dict):
        return ["- %s is not an object, so nothing in it is in force." % SETTINGS_RELATIVE]

    lines = []

    deny = ((settings.get("permissions") or {}).get("deny")) or []
    deny = [rule for rule in deny if isinstance(rule, str)]
    if deny:
        covered = [label for label, pattern in DENY_SUBJECTS if any(pattern.search(rule) for rule in deny)]
        detail = ", covering " + ", ".join(covered) if covered else ""
        lines.append("- %d deny rules are in force in %s%s." % (len(deny), SETTINGS_RELATIVE, detail))
    else:
        lines.append("- No deny rules are configured in %s." % SETTINGS_RELATIVE)

    hooks = settings.get("hooks")
    if isinstance(hooks, dict) and hooks:
        for event in sorted(hooks):
            scripts = sorted(set(re.findall(r"hooks/([A-Za-z0-9_.-]+\.py)", json.dumps(hooks[event]))))
            named = ", ".join(scripts) if scripts else "an unnamed command"
            lines.append("- %s runs %s." % (event, named))
    else:
        lines.append("- No hooks are registered.")

    return lines


def protected_report(root):
    """Whether the protected-paths mechanism is present, and whether it currently guards anything."""
    patterns = read_lines(root, PATHS_RELATIVE)
    if not (root / PATHS_RELATIVE).is_file():
        return "- %s does not exist, so no file is write-protected." % PATHS_RELATIVE
    if not patterns:
        return (
            "- %s exists but lists nothing, so the protected-paths hook is present and inert. "
            "Nothing is write-protected." % PATHS_RELATIVE
        )

    matched = []
    for pattern in patterns:
        pattern = pattern.replace("\\", "/")
        try:
            if re.search(r"[*?\[]", pattern):
                matched.extend(path for path in root.glob(pattern) if path.is_file())
            elif (root / pattern).is_file():
                matched.append(root / pattern)
        except (OSError, ValueError, IndexError):
            continue

    names = sorted({path.relative_to(root).as_posix() for path in matched})
    head = "- %d protected path %s in %s, currently matching %d file%s" % (
        len(patterns),
        "entry" if len(patterns) == 1 else "entries",
        PATHS_RELATIVE,
        len(names),
        "" if len(names) == 1 else "s",
    )
    if not names:
        return head + ". Nothing is write-protected yet: the entries name files that do not exist, and each starts protecting the moment it does."
    shown = names[:12]
    tail = "" if len(names) == len(shown) else ", and %d more" % (len(names) - len(shown))
    return (
        head
        + ". Write-protected through the file tools and the shell, and a shell command naming one is\n"
        + "  refused unless it only reads it:\n"
        + "".join("  - %s\n" % name for name in shown).rstrip("\n")
        + tail
    )


def main():
    root = hook_io.project_root()

    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    head = git(root, "log", "-1", "--format=%h %s") or "unknown"
    status = git(root, "status", "--short")
    tree = "dirty\n" + status if status else "clean"

    guardrails = "\n".join(
        ["Structural guardrails in force, generated from the configuration rather than restated:"]
        + settings_report(root)
        + [protected_report(root)]
        + ["", CAVEAT]
    )

    parts = [
        """Re-asserted at session start, including after compaction. These are constraints, not suggestions.

Live repository state, read just now rather than remembered:
- branch: {branch}
- HEAD: {head}
- working tree: {tree}""".format(branch=branch, head=head, tree=tree),
        "Verbatim from CLAUDE.md:\n\n" + (claude_md_sections(root, sections_wanted(root)) or FALLBACK_SECURITY),
        guardrails,
    ]

    try:
        notes = (root / NOTES_RELATIVE).read_text(encoding="utf-8").strip()
    except OSError:
        notes = ""
    if notes:
        parts.append(notes)

    context = "\n\n".join(parts)

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
