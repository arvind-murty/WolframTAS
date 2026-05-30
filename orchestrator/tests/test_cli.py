from __future__ import annotations

import json
from pathlib import Path

from wolftas_orchestrator.cli import main


def test_fixture_pipeline_writes_exact_solution(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output = tmp_path / "exact_solution.json"

    exit_code = main(
        [
            str(repo_root / "examples/simple_jump/request.json"),
            "--approx-solution",
            str(repo_root / "examples/simple_jump/approx_solution.json"),
            "--exact-solution-out",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "solved"
    assert payload["angles_discrete"][0]["yaw_index"] == 0
