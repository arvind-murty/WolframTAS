"""Guard the shared movement-constants table.

The imu/mmu physics now lives in ONE place: tools/gen_movement_constants.py emits
movement_constants.json for the orchestrator/Wolfram path and the Python solver.
These tests make sure the committed artifact is not stale w.r.t. the generator,
and that the numbers the orchestrator reads from the JSON match the numbers the
solver reports in its derived_model block.

Needs numpy 1.26 (the generator); no Wolfram required.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = REPO_ROOT / "orchestrator/wolframtas_orchestrator/movement_constants.json"
GEN_PATH = REPO_ROOT / "tools/gen_movement_constants.py"
RETENTION_MEDIA = ["flat_ground", "air", "slime", "ice", "water", "lava", "none"]


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_movement_constants", GEN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_artifacts_match_generator() -> None:
    gen = _load_generator()
    table = gen.build()

    committed_json = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    assert committed_json == table, "movement_constants.json is stale; re-run tools/gen_movement_constants.py"


def _solver_retention() -> dict[str, float]:
    sys.path.insert(0, str(REPO_ROOT / "orchestrator"))
    from wolframtas_orchestrator.python_solver import solve

    n = len(RETENTION_MEDIA)
    slots = [
        {
            "slot": i,
            "kind": "movement",
            "controls": {"forward": 0, "strafe": 0, "jump": False, "sneak": False, "sprint": False},
            "acceleration": {"medium": "air", "input": "no45_forward"},
            "retention": {"medium": medium},
        }
        for i, medium in enumerate(RETENTION_MEDIA, start=1)
    ]
    request = {
        "version": 1,
        "n": n,
        "angle_domain": {"table_size": 65536},
        "initial_state": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "yaw": 0.0,
            "pitch": 0.0,
            "on_ground": False,
        },
        "movement_plan": {"version": 1, "slot_indexing": "1_based", "slots": slots},
        "optimal_solution": {
            "status": "optimal",
            "objective_value": 0.0,
            "movement_directions": [{"slot": i, "radians": 0.0, "degrees": 0.0} for i in range(1, n + 1)],
        },
    }
    derived = solve(request)["derived_model"]
    return {medium: derived["imux"][i] for i, medium in enumerate(RETENTION_MEDIA)}


def test_orchestrator_json_matches_python_solver() -> None:
    sys.path.insert(0, str(REPO_ROOT / "orchestrator"))
    from wolframtas_orchestrator.movement_model import retention_for

    solver = _solver_retention()
    for medium in RETENTION_MEDIA:
        assert retention_for(medium) == solver[medium], f"retention drift for {medium}"
