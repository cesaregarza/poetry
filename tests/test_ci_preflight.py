import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ci_preflight.py"


def test_ci_preflight_help_does_not_need_a_database():
    result = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--image-tag" in result.stdout


@pytest.mark.parametrize(
    "database", ["", "postgresql://db.example/poetry", "sqlite://localhost/db"]
)
def test_ci_preflight_rejects_unsafe_database_before_running_commands(database):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        env=os.environ | {"DATABASE_URL": database},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "DATABASE_URL" in result.stderr
