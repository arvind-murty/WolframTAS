from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_repair_fixture_runs_real_wolfram_and_exact_solver(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]

    strict_output = tmp_path / "strict.json"
    relaxed_output = tmp_path / "relaxed.json"
    exact_input_output = tmp_path / "exact_input.json"
    exact_output = tmp_path / "exact.json"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "orchestrator")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "wolframtas_orchestrator",
            "solve-exact-input",
            str(repo_root / "examples/simple_jump/repair_exact_solver_input.json"),
            "--strict-out",
            str(strict_output),
            "--relaxed-out",
            str(relaxed_output),
            "--exact-input-out",
            str(exact_input_output),
            "--exact-out",
            str(exact_output),
        ],
        cwd=repo_root,
        env=env,
        check=True,
    )

    strict = json.loads(strict_output.read_text(encoding="utf-8"))
    relaxed = json.loads(relaxed_output.read_text(encoding="utf-8"))
    exact_input = json.loads(exact_input_output.read_text(encoding="utf-8"))
    exact = json.loads(exact_output.read_text(encoding="utf-8"))

    assert strict["status"] == "optimal"
    assert relaxed["status"] == "optimal"
    assert relaxed["diagnostics"]["objective_deviation"] <= 0.001
    assert exact_input["optimal_solution"]["diagnostics"]["stage"] == "relaxed"
    assert exact["status"] == "solved"
    assert float(exact["diagnostics"]["final_residual_norm"]) == 0.0
    assert isinstance(exact["diagnostics"]["changed_angle_indices"], list)
