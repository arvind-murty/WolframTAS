from __future__ import annotations

import json
from pathlib import Path

from wolframtas_orchestrator.cli import main


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


def test_render_mathematica_writes_wolfram_script(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output = tmp_path / "generated.wls"

    exit_code = main(
        [
            "render-mathematica",
            str(repo_root / "examples/simple_jump/inertia_mathematica_input.json"),
            "--out",
            str(output),
        ]
    )

    assert exit_code == 0
    script = output.read_text(encoding="utf-8")
    assert "Imux =" in script
    assert "obj = Z[F, 1];" in script
    assert "x_inertia_hit_slot_1_positive_bound" in script
    assert "z_inertia_avoid_slot_1_positive_avoid" in script


def test_run_mathematica_invokes_wolframscript_and_writes_json(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fake_wolframscript = tmp_path / "fake_wolframscript"
    output = tmp_path / "approx_solution.json"

    fake_wolframscript.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "assert sys.argv[1] == '-file'\n"
        "print(json.dumps({'version': 1, 'status': 'optimal', 'diagnostics': {'script': sys.argv[2], 'input': sys.argv[3]}}))\n",
        encoding="utf-8",
    )
    fake_wolframscript.chmod(0o755)

    exit_code = main(
        [
            "run-mathematica",
            str(repo_root / "examples/simple_jump/inertia_mathematica_input.json"),
            "--approx-out",
            str(output),
            "--wolframscript",
            str(fake_wolframscript),
            "--optimizer-script",
            str(repo_root / "mathematica/optimize.wls"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "optimal"
    assert payload["diagnostics"]["script"].endswith("mathematica/optimize.wls")
