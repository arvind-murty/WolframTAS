from __future__ import annotations

import json
from pathlib import Path

from wolframtas_orchestrator.cli import exact_template_to_mathematica_problem, main


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
    assert payload["macro_rows"][0]["w"] is True
    assert payload["macro_rows"][0]["j"] is True
    assert payload["diagnostics"]["mode"] == "fixture"


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


def test_render_mathematica_relaxes_typed_position_bounds(tmp_path: Path) -> None:
    input_path = tmp_path / "typed.json"
    output = tmp_path / "generated.wls"
    input_path.write_text(
        json.dumps(
            {
                "version": 1,
                "slot_indexing": "1_based",
                "n": 1,
                "arrays": {"imux": [0.91], "imuz": [0.91], "mmu": [0.02]},
                "objective": {"sense": "maximize", "expression": "Z[F, 1]"},
                "constraints": [
                    {
                        "id": "landing",
                        "type": "position_bounds",
                        "slot": 1,
                        "min_x": 0.00002,
                        "min_z": 1.0,
                        "max_z": 2.0,
                        "mathematica_tolerance": 0.0001,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["render-mathematica", str(input_path), "--out", str(output)])

    assert exit_code == 0
    script = output.read_text(encoding="utf-8")
    assert "X[F, 1] >= (0.00002 - 0.0001)" in script
    assert "2e-05" not in script
    assert "Z[F, 1] >= (1.0 - 0.0001)" in script
    assert "Z[F, 1] <= (2.0 + 0.0001)" in script


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


def test_exact_template_inertia_hit_adds_wolfram_event_and_zeroes_axis() -> None:
    problem = exact_template_to_mathematica_problem(
        {
            "version": 1,
            "name": "inertia-hit",
            "slot_indexing": "1_based",
            "n": 1,
            "movement_plan": {
                "version": 1,
                "slot_indexing": "1_based",
                "slots": [
                    {
                        "slot": 1,
                        "kind": "movement",
                        "controls": {"forward": 1, "strafe": 0, "jump": False, "sneak": False, "sprint": True},
                        "acceleration": {"medium": "air"},
                        "retention": {"medium": "air"},
                    }
                ],
            },
            "constraints": [],
            "inertia_events": [{"id": "hit_x", "type": "hit", "axis": "x", "slot": 1}],
            "exact_objective": {"type": "position", "axis": "z", "slot": 1},
        },
        constraint_tolerance=0.0,
        fill_missing_tolerance=False,
    )

    assert problem["arrays"]["imux"] == [0.0]
    assert problem["arrays"]["imuz"] == [0.9100000262260437]
    assert problem["inertia_events"] == [
        {
            "id": "hit_x",
            "type": "hit",
            "axis": "x",
            "slot": 1,
            "retention_multiplier": 0.9100000262260437,
        }
    ]


def test_run_mathematica_staged_rejects_large_objective_drift(tmp_path: Path) -> None:
    input_path = tmp_path / "problem.json"
    strict_output = tmp_path / "strict.json"
    relaxed_output = tmp_path / "relaxed.json"
    fake_wolframscript = tmp_path / "fake_wolframscript"
    input_path.write_text(
        json.dumps(
            {
                "version": 1,
                "slot_indexing": "1_based",
                "n": 1,
                "arrays": {"imux": [0.91], "imuz": [0.91], "mmu": [0.02]},
                "objective": {"sense": "maximize", "expression": "Z[F, 1]"},
                "constraints": [{"id": "landing", "type": "position_bounds", "slot": 1, "min_z": 1.0}],
            }
        ),
        encoding="utf-8",
    )
    fake_wolframscript.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "problem = json.load(open(sys.argv[3]))\n"
        "expression = problem['constraints'][0]['expression']\n"
        "objective = 1.0 if '- 0.0001' not in expression else 1.01\n"
        "print(json.dumps({'version': 1, 'status': 'optimal', 'objective_value': objective, 'movement_directions': []}))\n",
        encoding="utf-8",
    )
    fake_wolframscript.chmod(0o755)

    try:
        main(
            [
                "run-mathematica-staged",
                str(input_path),
                "--strict-out",
                str(strict_output),
                "--relaxed-out",
                str(relaxed_output),
                "--wolframscript",
                str(fake_wolframscript),
                "--solution-tolerance",
                "0.001",
            ]
        )
    except RuntimeError as error:
        assert "exceeding solution_tolerance" in str(error)
    else:
        raise AssertionError("staged Mathematica run should reject objective drift")


def test_solve_exact_input_runs_staged_math_and_exact_solver(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    strict_output = tmp_path / "strict.json"
    relaxed_output = tmp_path / "relaxed.json"
    exact_input_output = tmp_path / "exact_input.json"
    exact_output = tmp_path / "exact.json"
    fake_wolframscript = tmp_path / "fake_wolframscript"
    fake_solver = tmp_path / "fake_solver"

    fake_wolframscript.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "problem = json.load(open(sys.argv[3]))\n"
        "for constraint in problem['constraints']:\n"
        "    assert 'e-' not in constraint['expression']\n"
        "    assert '0.00002' in constraint['expression']\n"
        "relaxed = any('- 0.0001' in c['expression'] or '+ 0.0001' in c['expression'] for c in problem['constraints'])\n"
        "print(json.dumps({\n"
        "  'version': 1,\n"
        "  'status': 'optimal',\n"
        "  'objective_value': 2.0 if relaxed else 1.9995,\n"
        "  'movement_directions': [{'slot': i + 1, 'radians': 0.0} for i in range(problem['n'])],\n"
        "  'points': []\n"
        "}))\n",
        encoding="utf-8",
    )
    fake_wolframscript.chmod(0o755)
    fake_solver.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "payload = json.load(sys.stdin)\n"
        "assert payload['optimal_solution']['objective_value'] == 2.0\n"
        "print(json.dumps({'version': 1, 'status': 'solved', 'diagnostics': {'n': payload['n']}}))\n",
        encoding="utf-8",
    )
    fake_solver.chmod(0o755)

    exit_code = main(
        [
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
            "--wolframscript",
            str(fake_wolframscript),
            "--solver-command",
            str(fake_solver),
        ]
    )

    assert exit_code == 0
    relaxed = json.loads(relaxed_output.read_text(encoding="utf-8"))
    exact_input = json.loads(exact_input_output.read_text(encoding="utf-8"))
    exact = json.loads(exact_output.read_text(encoding="utf-8"))
    assert relaxed["diagnostics"]["stage"] == "relaxed"
    assert exact_input["optimal_solution"]["objective_value"] == 2.0
    assert exact["status"] == "solved"
