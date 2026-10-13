#!/usr/bin/env python3
"""Thin script entry point that forwards execution into the packaged CLI."""

from __future__ import annotations

import sys

from acsl_tool.cli import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
