#!/usr/bin/env python3
"""Run the frozen Approve-to-Pay task set. See approvetopay/cli.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from approvetopay.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
