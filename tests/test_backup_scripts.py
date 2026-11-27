"""Static safety checks for the local backup and restore scripts."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_backup_and_restore_scripts_pass_bash_syntax_check():
    for name in ("backup-local.sh", "restore-local.sh"):
        result = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_qdrant_is_published_to_loopback_only():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    qdrant = compose.split("  qdrant:", 1)[1].split("\n  api:", 1)[0]
    assert '"127.0.0.1:6333:6333"' in qdrant
    assert '"0.0.0.0:6333:6333"' not in qdrant


def test_backup_and_restore_use_private_compose_network():
    for name in ("backup-local.sh", "restore-local.sh"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "docker inspect" in source
        assert '--network "$QDRANT_NETWORK"' in source
        assert "curlimages/curl:8.12.1" in source
        assert "http://localhost:6333" not in source
