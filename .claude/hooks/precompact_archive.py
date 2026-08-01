"""PreCompact hook: copy the raw transcript before compaction rewrites the window.

Compaction keeps what is recent, not what matters. A summary decides for you which of the last
hundred records survive, and it has already thrown away subagent research while keeping a file
write acknowledgement. This hook takes the complete record instead of a summary of it: the
transcript file Claude Code is about to compact, copied verbatim, before it is touched.

Registered for both triggers, manual and auto, because the auto one is the one nobody is watching.

The archive never blocks compaction. A failed copy is worth a warning, not a wedged session that
cannot compact and cannot continue.

.claude/transcripts/ is gitignored. Transcripts are unencrypted plaintext of everything a tool
printed, which in this repository means database credentials the moment a command echoes .env.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path

import hook_io

DEST_RELATIVE = ".claude/transcripts"

# session_id lands in a filename, so it is treated as untrusted input rather than as a UUID.
UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def main():
    payload = hook_io.read_payload()
    root = hook_io.project_root()

    transcript = payload.get("transcript_path")
    if not transcript or not isinstance(transcript, str):
        hook_io.emit({"systemMessage": "PreCompact: no transcript_path in the payload, nothing archived."})

    source = Path(transcript)
    if not source.is_absolute():
        source = root / source
    if not source.is_file():
        hook_io.emit({"systemMessage": "PreCompact: transcript %s is missing, nothing archived." % source})

    session = UNSAFE.sub("-", str(payload.get("session_id") or "unknown"))[:64]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = root / DEST_RELATIVE / ("%s-%s.jsonl" % (stamp, session))

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(destination))
    except OSError as error:
        hook_io.emit({"systemMessage": "PreCompact: could not archive the transcript: %s" % error})

    trigger = payload.get("trigger") or "unknown"
    hook_io.emit(
        {
            "systemMessage": "Transcript archived before %s compaction: %s/%s"
            % (trigger, DEST_RELATIVE, destination.name)
        }
    )


main()
