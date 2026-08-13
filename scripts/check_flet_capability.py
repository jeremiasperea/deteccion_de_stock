"""Standalone capability check for the Flet ``Image.src_bytes`` assumption.

Design decision D-G pins ``flet>=0.84.0,<0.86.0`` on the assumption that the
resolved Flet install exposes ``Image.src_bytes`` for zero-copy raw-byte
frame rendering (FIX 10). This script asserts that capability against
whatever Flet version is *actually* resolved, instead of trusting the pin
blindly. It is run both by CI (``.github/workflows/ci.yml``, the
``flet-capability`` job) and locally:

    .venv-linux/bin/python scripts/check_flet_capability.py

Exits non-zero and prints the resolved version when the capability is
missing, per design Open Question 2: "the <0.86.0 ceiling is inferred from
the docstring's claimed 0.85.1, not from an installed runtime."
"""

from __future__ import annotations

import sys

import flet as ft


def main() -> int:
    resolved_version = getattr(ft, "__version__", "unknown")
    print(f"Resolved flet version: {resolved_version}")

    has_src_bytes = hasattr(ft.Image, "src_bytes")
    print(f"hasattr(ft.Image, 'src_bytes'): {has_src_bytes}")

    if not has_src_bytes:
        print(
            "FAIL: ft.Image.src_bytes capability is missing on the "
            f"resolved flet {resolved_version}. D-G's assumption "
            "(design Open Question 2) does not hold for this version.",
            file=sys.stderr,
        )
        return 1

    print("OK: ft.Image.src_bytes capability present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
