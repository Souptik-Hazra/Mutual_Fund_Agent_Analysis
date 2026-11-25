"""Regression tests for the Alembic graph and revision template."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_revision_template_uses_active_mako_expressions():
    path = Path(__file__).parents[1] / "migrations" / "script.py.mako"
    source = path.read_text(encoding="utf-8")
    assert "\\${" not in source
    assert "${repr(up_revision)}" in source
    assert '${upgrades if upgrades else "pass"}' in source
    assert '${downgrades if downgrades else "pass"}' in source


def test_migration_graph_has_single_expected_financial_head():
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0009_metadata_and_distributions"]
    revision = scripts.get_revision("0009_metadata_and_distributions")
    assert revision.down_revision == "0008_investor_ledger"
