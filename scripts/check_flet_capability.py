"""Standalone capability check for the Flet ``Image.src`` bytes assumption.

Design decision D-G pins ``flet>=0.84.0,<0.86.0`` on the assumption that the
resolved Flet install accepts raw ``bytes`` assigned directly to
``Image.src`` for zero-copy frame rendering. This script asserts that
capability functionally, against whatever Flet version is *actually*
resolved, instead of trusting the pin blindly. It is run both by CI
(``.github/workflows/ci.yml``, the ``flet-capability`` job) and locally:

    .venv-linux/bin/python scripts/check_flet_capability.py

Exits non-zero and prints the resolved version when the capability is
missing.

Correction (see ``openspec/changes/refactor-clean-architecture/explore.md``
section 1): an earlier version of this script asserted
``hasattr(ft.Image, "src_bytes")``. That assertion was based on a false
premise — Flet's website documentation lists a separate ``Image.src_bytes``
property, but the *installed* package (verified for both ``flet==0.84.0``
and ``flet==0.85.3``, the full pinned range) has no such attribute at all;
``Image.src`` has always accepted ``bytes`` directly in this Flet
generation. The old assertion therefore failed unconditionally, independent
of any real regression. This script now performs a positive functional
check instead of attribute sniffing: it constructs an ``Image`` with a
``bytes`` value and asserts the value survives as ``bytes``.
"""

from __future__ import annotations

import sys

import flet as ft


def main() -> int:
    resolved_version = getattr(ft, "__version__", "unknown")
    print(f"Resolved flet version: {resolved_version}")

    probe = b"\xff\xd8\xff\xe0probe-jpeg-bytes"
    try:
        image = ft.Image(src=probe)
        accepts_bytes = isinstance(image.src, bytes) and image.src == probe
    except Exception as exc:  # pragma: no cover - defensive, reported below
        print(
            "FAIL: constructing ft.Image(src=<bytes>) raised "
            f"{exc.__class__.__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"ft.Image(src=<bytes>) preserves bytes: {accepts_bytes}")

    if not accepts_bytes:
        print(
            "FAIL: ft.Image.src does not accept/preserve bytes on the "
            f"resolved flet {resolved_version}. D-G's assumption "
            "does not hold for this version.",
            file=sys.stderr,
        )
        return 1

    print("OK: Image.src accepts bytes directly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
