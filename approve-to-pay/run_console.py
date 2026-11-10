#!/usr/bin/env python3
"""Launch the Approve-to-Pay approval console. See approvetopay/console.py.

    python3 run_console.py              # http://127.0.0.1:8765
    python3 run_console.py --port 9000
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from approvetopay.console import main

if __name__ == "__main__":
    raise SystemExit(main())
