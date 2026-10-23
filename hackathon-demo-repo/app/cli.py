"""CLI entry point: `python3 -m app.cli` prints the human report."""

import sys

from app.report import human_report


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Tier-3 seed issue: --json is not implemented yet.
    print(human_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
