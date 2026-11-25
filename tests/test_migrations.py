"""Regression test for Alembic revision template interpolation."""

from pathlib import Path


def test_revision_template_uses_active_mako_expressions():
    path = Path(__file__).parents[1] / "migrations" / "script.py.mako"
    source = path.read_text(encoding="utf-8")
    assert "\\${" not in source
    assert "${repr(up_revision)}" in source
    assert '${upgrades if upgrades else "pass"}' in source
    assert '${downgrades if downgrades else "pass"}' in source
