"""Domain layer — pure business logic, stdlib-only imports.

No infrastructure types (cv2, flet, ultralytics, pandas, numpy) may be
imported here, directly or under TYPE_CHECKING. Enforced by
tests/architecture/test_dependency_rule.py (Phase 1b).
"""
