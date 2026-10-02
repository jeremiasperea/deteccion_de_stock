"""Dependency rule (D-F): domain imports only stdlib or depot_vision.domain.

Static ``ast`` walk over ``src/depot_vision/domain/**/*.py``, including
imports nested in functions or ``TYPE_CHECKING`` blocks. Known gap: dynamic
``importlib`` / ``__import__`` use is not detected.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

DOMAIN_DIR = Path(__file__).resolve().parents[2] / "src" / "depot_vision" / "domain"
ALLOWED_PREFIX = "depot_vision.domain"


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                modules.append("." * node.level + (node.module or ""))
            elif node.module:
                modules.append(node.module)
    return modules


def _is_allowed(module: str) -> bool:
    if module.startswith("."):
        return False  # relative imports hide the layer; require absolute ones
    if module == ALLOWED_PREFIX or module.startswith(ALLOWED_PREFIX + "."):
        return True
    return module.split(".")[0] in sys.stdlib_module_names


def _violations(source_dir: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(source_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.extend(
            f"{path.relative_to(source_dir)}: imports {module}"
            for module in _imported_modules(tree)
            if not _is_allowed(module)
        )
    return found


def test_domain_package_exists() -> None:
    assert any(DOMAIN_DIR.rglob("*.py"))


def test_domain_imports_only_stdlib_or_domain() -> None:
    assert _violations(DOMAIN_DIR) == []


def test_checker_flags_a_forbidden_import(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("import numpy\nfrom depot_vision.adapters import x\n")
    (tmp_path / "nested.py").write_text("def f():\n    import cv2\n")

    assert _violations(tmp_path) == [
        "bad.py: imports numpy",
        "bad.py: imports depot_vision.adapters",
        "nested.py: imports cv2",
    ]
