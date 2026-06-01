"""Cross-model consistency: the Python orchestrator derivation (for the
Mathematica stage) and the C++ exact solver must derive the same movement arrays
from a shared movement_plan. This guards against the two independent
implementations drifting (e.g. a retention medium supported on one side only, or
a 1-ULP value difference).

Uses no-input slots so mmu is 0 on both sides and the comparison isolates
retention (imux/imuz) across every supported medium. Needs the built solver; no
Wolfram required.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SOLVER = REPO_ROOT / "solver/build/wolframtas_solver"
RETENTION_MEDIA = ["flat_ground", "air", "slime", "ice", "water", "lava", "none"]


def build_plan() -> dict:
    slots = []
    for index, medium in enumerate(RETENTION_MEDIA, start=1):
        slots.append(
            {
                "slot": index,
                "kind": "movement",
                "controls": {"forward": 0, "strafe": 0, "jump": False, "sneak": False, "sprint": False},
                "acceleration": {"medium": "air", "input": "no45_forward"},
                "retention": {"medium": medium},
            }
        )
    return {"version": 1, "slot_indexing": "1_based", "slots": slots}


def python_arrays(plan: dict) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "orchestrator"))
    from wolframtas_orchestrator.movement_model import derive_movement_model

    return derive_movement_model(plan)["arrays"]


def cpp_arrays(plan: dict) -> dict:
    n = len(plan["slots"])
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
        "movement_plan": plan,
        "optimal_solution": {
            "status": "optimal",
            "objective_value": 0.0,
            "movement_directions": [{"slot": i, "radians": 0.0, "degrees": 0.0} for i in range(1, n + 1)],
        },
    }
    completed = subprocess.run(
        [str(SOLVER)], input=json.dumps(request), text=True, capture_output=True, check=True
    )
    return json.loads(completed.stdout)["derived_model"]


def test_python_and_cpp_derive_identical_arrays() -> None:
    assert SOLVER.exists(), "build solver first with: cmake --build solver/build"
    plan = build_plan()
    py = python_arrays(plan)
    cpp = cpp_arrays(plan)
    # Per-medium so a failure names the offending medium.
    for index, medium in enumerate(RETENTION_MEDIA):
        assert py["imux"][index] == cpp["imux"][index], f"imux drift for {medium}"
        assert py["imuz"][index] == cpp["imuz"][index], f"imuz drift for {medium}"
        assert py["mmu"][index] == cpp["mmu"][index], f"mmu drift for {medium}"
