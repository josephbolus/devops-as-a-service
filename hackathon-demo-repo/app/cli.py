"""CLI entry point: `python3 -m app.cli` prints the human report."""

import json
import sys

from app.report import REPORT, human_report


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--json" in argv:
        print(json.dumps(REPORT))
        return 0
    print(human_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
