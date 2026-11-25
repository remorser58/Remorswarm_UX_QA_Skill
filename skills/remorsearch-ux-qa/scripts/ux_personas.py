#!/usr/bin/env python3
"""Run the portable persona library and UX task CLI without installing a package."""
from pathlib import Path
import sys

if sys.version_info < (3, 10):
    print("Python 3.10 or newer is required.", file=sys.stderr)
    raise SystemExit(2)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uxpersonas.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

