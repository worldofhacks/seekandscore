"""Deployment boundary for the shared worker implementation."""

from seekandscore.worker.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
