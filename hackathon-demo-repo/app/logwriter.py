"""Service log writer.

Expansion seed issue #7 (resource exhaustion / disk, intentional —
do not fix in the scaffold): the writer appends forever and never
rotates, so the log file grows without bound until the disk fills
and the service first stops logging and then crashes. A max_bytes
limit is configured but never acted on.
"""
from pathlib import Path


class LogWriter:
    """Append lines to `path`, rotating at `max_bytes`.

    Rotation contract: before writing a line that would make the
    active file exceed max_bytes, rename the active file to
    '<path>.1' (replacing any previous backup) and start a fresh
    active file. The line itself is then written to the fresh file.
    """

    def __init__(self, path, max_bytes=1024):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.backup_path = Path(str(path) + ".1")

    def write(self, line):
        data = (line + "\n").encode("utf-8")
        # BUG: max_bytes is never checked — no rotation ever happens,
        # so the active file grows without bound.
        with self.path.open("ab") as fh:
            fh.write(data)

    def current_size(self):
        return self.path.stat().st_size if self.path.exists() else 0
