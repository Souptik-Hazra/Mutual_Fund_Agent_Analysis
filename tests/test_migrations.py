"""Regression test for Alembic revision template rendering."""
from pathlib import Path
from mako.template import Template

def test_revision_template_renders_valid_python():
    path = Path(__file__).parents[1] / "migrations" / "script.py.mako"
    template = Template(filename=str(path), strict_undefined=True)
    rendered = template.render(message='test', up_revision='abc', down_revision=None, create_date='2026-11-25', imports='', repr=repr, branch_labels=None, depends_on=None, upgrades='pass', downgrades='pass', filters={'comma': lambda value, name: ', '.join(value) if value else 'None'})
    compile(rendered, str(path), "exec")
    assert 'revision: str = ' in rendered
