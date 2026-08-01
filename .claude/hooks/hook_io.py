"""Shared plumbing for this repository's Claude Code hooks.

Every hook here obeys the same contract: read one JSON payload on stdin, write at most one JSON
object to stdout, and always exit 0. Claude Code only parses hook stdout when the exit code is 0,
so a crashing hook must never turn into an accidental block or an accidental allow.

These are Python, not PowerShell, so one script covers Windows and macOS. The launcher in
settings.json picks the interpreter with `case "$OS" in Windows_NT) PY=python;; *) PY=python3;;`
because the two platforms disagree on the name: macOS installs `python3` and often has no
`python`, while Windows ships a `python3` stub that only advertises the Microsoft Store and exits
49 without running anything.
"""

import json
import os
import sys
from pathlib import Path


def read_payload():
    """The hook input as a dict, or an empty dict if stdin held nothing parseable."""
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def project_root():
    """The repository root.

    Claude Code exports CLAUDE_PROJECT_DIR for every hook. The fallback walks up from this file
    (.claude/hooks/<script>.py) so the hooks still work when run by hand from another directory.
    """
    from_env = os.environ.get("CLAUDE_PROJECT_DIR")
    if from_env:
        return Path(from_env)
    return Path(__file__).resolve().parents[2]


def emit(payload=None):
    """Write the hook result, if any, and exit 0. No payload means "no opinion, proceed"."""
    if payload:
        sys.stdout.write(json.dumps(payload))
    sys.exit(0)
