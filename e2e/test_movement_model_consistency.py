"""Guard the shared movement-constants table.

The imu/mmu physics now lives in ONE place: tools/gen_movement_constants.py emits
both movement_constants.json (orchestrator/Wolfram) and
movement_constants_generated.hpp (C++ solver). These tests make sure the two
committed artifacts are not stale w.r.t. the generator, and that the numbers the
orchestrator reads from the JSON match the numbers the solver actually compiled
in and derives at runtime (catches a hand-edited JSON or a stale solver build).

Needs numpy 1.26 (the generator) and the built solver; no Wolfram required.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOLVER = REPO_ROOT / "solver/build/wolframtas_solver"
JSON_PATH = REPO_ROOT / "orchestrator/wolframtas_orchestrator/movement_constants.json"
HPP_PATH = REPO_ROOT / "solver/include/wolframtas/movement_constants_generated.hpp"
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

    expected_hpp = HPP_PATH.read_text(encoding="utf-8")
    tmp = HPP_PATH.with_suffix(".hpp.regen")
    try:
        gen.emit_hpp(table, tmp)
        assert tmp.read_text(encoding="utf-8") == expected_hpp, (
            "movement_constants_generated.hpp is stale; re-run tools/gen_movement_constants.py"
        )
    finally:
        if tmp.exists():
            tmp.unlink()


def _cpp_retention() -> dict[str, float]:
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
    completed = subprocess.run(
        [str(SOLVER)], input=json.dumps(request), text=True, capture_output=True, check=True
    )
    derived = json.loads(completed.stdout)["derived_model"]
    return {medium: derived["imux"][i] for i, medium in enumerate(RETENTION_MEDIA)}


def test_orchestrator_json_matches_compiled_solver() -> None:
    assert SOLVER.exists(), "build solver first with: cmake --build solver/build"
    sys.path.insert(0, str(REPO_ROOT / "orchestrator"))
    from wolframtas_orchestrator.movement_model import retention_for

    cpp = _cpp_retention()
    for medium in RETENTION_MEDIA:
        assert retention_for(medium) == cpp[medium], f"retention drift for {medium} (rebuild solver?)"
