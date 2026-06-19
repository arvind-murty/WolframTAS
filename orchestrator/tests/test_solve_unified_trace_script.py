from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_solve_unified_trace_script_writes_compact_output(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fake_wolframscript = tmp_path / "fake_wolframscript"
    output = tmp_path / "unified.md"

    fake_wolframscript.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "problem = json.load(open(sys.argv[3]))\n"
        "relaxed = any('+ 0.0001' in c['expression'] or '- 0.0001' in c['expression'] for c in problem['constraints'])\n"
        "points = [{'slot': i, 'x': 0.0, 'z': 0.1 * i} for i in range(problem['n'] + 1)]\n"
        "print(json.dumps({\n"
        "  'version': 1,\n"
        "  'status': 'optimal',\n"
        "  'objective_value': points[-1]['z'] + (0.00001 if relaxed else 0.0),\n"
        "  'movement_directions': [{'slot': i + 1, 'radians': 0.0, 'degrees': 0.0} for i in range(problem['n'])],\n"
        "  'points': points\n"
        "}))\n",
        encoding="utf-8",
    )
    fake_wolframscript.chmod(0o755)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "orchestrator")
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/solve_unified_trace.py"),
            str(repo_root / "examples/simple_jump/repair_exact_solver_input.json"),
            "--out",
            str(output),
            "--wolframscript",
            str(fake_wolframscript),
            "--default-relaxed-tolerance",
            "0.0001",
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = output.read_text(encoding="utf-8")
    assert report.startswith("# WolframTAS Unified Trace:")
    assert "## Strict Mathematica" in report
    assert "## Relaxed Mathematica" in report
    assert "## Exact Solver" in report
    assert "## Macro Rows" in report
    assert "## Macro CSV" in report
    assert "| slot | x | z | vx | vz | yaw_degrees | movement_direction_degrees |" in report
    assert "| tick | x | z | vx | vz | yaw_degrees | yaw_index |" in report
    assert "| 0 | 0.0 | 0.0 | 0.0 | 0.0 |  |  |" in report
    assert "```csv\nW,A,S,D,P,N,J,YAW,PITCH,L,R,COUNT,H\n" in report
