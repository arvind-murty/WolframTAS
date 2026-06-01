"""Command-string parity: parse mothball commands, run the C++ solver on each
derived movement_plan, and assert each matches the vendored mothball simulator.

The vendored engine needs numpy 1.26 + evalidate (the .venv-oracle venv), which
brew's pytest python lacks, so this shells out to that interpreter via
check_command_sim.py (which checks the full DEFAULT_COMMANDS list). Skips if the
venv or solver isn't built. To add a case, edit DEFAULT_COMMANDS in that file.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VENV_PY = REPO / ".venv-oracle/bin/python"
SOLVER = REPO / "solver/build/wolframtas_solver"
CHECKER = REPO / "e2e/check_command_sim.py"


@pytest.mark.skipif(not VENV_PY.exists(), reason="numpy-1.26 venv (.venv-oracle) not set up")
@pytest.mark.skipif(not SOLVER.exists(), reason="solver not built")
def test_commands_match_mothball() -> None:
    completed = subprocess.run(
        [str(VENV_PY), str(CHECKER)],
        cwd=REPO,
        env={"PYTHONPATH": str(REPO / "orchestrator")},
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
