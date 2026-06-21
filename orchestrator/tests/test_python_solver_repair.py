from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from numpy import float32 as fl
from wolframtas_orchestrator.block_route import block_route_to_candidate_bundle
from wolframtas_orchestrator.python_solver import solve

_VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from cogs.movement.context import Context  # noqa: E402
from cogs.movement.player import Player  # noqa: E402
from cogs.movement import parsers  # noqa: E402


def _multi_tick_x_repair_case() -> dict:
    movement_slots = []
    directions = [{"slot": 1, "radians": 0.0}]
    for slot in range(2, 5):
        movement_slots.append(
            {
                "slot": slot,
                "kind": "movement",
                "controls": {
                    "forward": 1,
                    "strafe": 0,
                    "jump": False,
                    "sneak": False,
                    "sprint": False,
                },
                "acceleration": {"medium": "air", "input": "no45_forward"},
                "retention": {"medium": "air"},
            }
        )
        directions.append({"slot": slot, "radians": 0.0})

    return {
        "version": 1,
        "slot_indexing": "1_based",
        "n": 4,
        "angle_domain": {"table_size": 65536},
        "initial_state": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "yaw": 0.0,
            "pitch": 0.0,
            "on_ground": False,
        },
        "movement_plan": {
            "version": 1,
            "slot_indexing": "1_based",
            "slots": [
                {"slot": 1, "kind": "init", "speed": 0.0, "imux": 0.91, "imuz": 0.91},
                *movement_slots,
            ],
        },
        "constraints": [
            {
                "id": "min_x",
                "type": "position_bounds",
                "slot": 4,
                "min_x": 0.00001,
                "exact_tolerance": 0.0,
            }
        ],
        "optimal_solution": {
            "status": "optimal",
            "objective_value": 0.0,
            "movement_directions": directions,
        },
    }


def test_repair_distributes_small_discrete_shortfall_across_ticks() -> None:
    solution = solve(_multi_tick_x_repair_case())

    assert solution["status"] == "solved"
    assert float(solution["diagnostics"]["final_residual_norm"]) == 0.0
    changed = solution["diagnostics"]["changed_angle_indices"]
    assert len(changed) > 1
    assert all(abs(change["delta"]) <= 2 for change in changed)


def test_explicit_repair_budget_is_respected() -> None:
    exact_input = copy.deepcopy(_multi_tick_x_repair_case())
    exact_input["exact_solver"] = {
        "max_repair_iterations": 1,
        "max_candidate_evaluations": 0,
        "top_k_moves": 4,
        "max_index_delta_per_iteration": 2,
    }

    solution = solve(exact_input)

    assert solution["status"] == "failed"
    assert float(solution["diagnostics"]["final_residual_norm"]) > 0.0
    assert solution["diagnostics"]["candidate_evaluations"] == 0


def test_repair_uses_compound_windows_for_multi_avoid_boundaries() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    route = json.loads((repo_root / "examples/block_route_multi_avoid/block_route.json").read_text(encoding="utf-8"))
    candidate = block_route_to_candidate_bundle(route)["candidates"][0]
    exact_input = candidate["exact_template"]
    exact_input["optimal_solution"] = {
        "status": "optimal",
        "objective_value": 9.475511385038725,
        "movement_directions": [
            {"slot": slot, "radians": radians}
            for slot, radians in [
                (1, 0.123),
                (2, 0.09623023309399126),
                (3, 0.14850256150835875),
                (4, 0.07073510481127646),
                (5, 0.07580466395507254),
                (6, 0.08173679960287843),
                (7, 0.08865730978121582),
                (8, 0.09664837628050287),
                (9, 0.10565087599241309),
                (10, 0.11523351520646401),
                (11, 0.12404499143904404),
                (12, 0.7315820101681351),
                (13, -0.010303733383511789),
                (14, -0.12769277371188006),
                (15, -0.3406710144072941),
                (16, -0.6263415187317635),
                (17, -1.0299079456343885),
                (18, -1.3998661123484333),
                (19, -0.9680036292837091),
                (20, 2.51859126820489),
                (21, 2.8174606392257013),
                (22, 2.9538350566958593),
                (23, -1.7660727315655175e-07),
                (24, -2.597752811927119e-09),
                (25, -1.5938296809378556e-09),
                (26, -8.395199418641902e-10),
                (27, -6.13171190550456e-10),
                (28, -4.76060761079104e-10),
                (29, -3.724359626122155e-10),
                (30, -3.7469498760671066e-10),
                (31, -3.775864749053063e-10),
                (32, -3.8138522559143185e-10),
                (33, -3.865291399156162e-10),
                (34, -3.9369981305486587e-10),
                (35, -4.0359883716799035e-10),
                (36, -4.1166484386406076e-10),
                (37, -2.3237984559505927e-10),
            ]
        ],
    }
    exact_input["exact_objective"]["target_value"] = 9.475511385038725
    exact_input["exact_objective"]["solution_tolerance"] = 0.001

    solution = solve(exact_input)

    assert solution["status"] == "solved"
    assert float(solution["diagnostics"]["final_residual_norm"]) == 0.0
    changed = solution["diagnostics"]["changed_angle_indices"]
    assert all(abs(change["delta"]) <= 2 for change in changed)
    assert any(
        later["slot"] == earlier["slot"] + 1 and later["delta"] == earlier["delta"]
        for earlier, later in zip(changed, changed[1:])
    )


def test_exact_states_match_emitted_macro_bucket_yaws() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    exact_input = copy.deepcopy(
        json.loads(
            (repo_root / "examples/p2p_zero_tol_demo/p2p_zero_tol_demo_exact_input.json").read_text(encoding="utf-8")
        )
    )
    solution = solve(exact_input)
    slots = exact_input["movement_plan"]["slots"]
    states = solution["states_exact"]
    rows = solution["macro_rows"]

    player = Player()
    ctx = Context(player, [{}], False, "xz")

    # The first slot is an external init vector. Seed mothball at the internal
    # position that corresponds to the solver's reported post-init state, then
    # replay the real macro movement ticks from there.
    init_state = states[1]
    init_x = float(init_state["position"]["x"])
    init_z = float(init_state["position"]["z"])
    init_vx = float(init_state["velocity"]["x"])
    init_vz = float(init_state["velocity"]["z"])
    for command in (
        f"setposx({init_x - init_vx})",
        f"setposz({init_z - init_vz})",
        f"setvx({init_vx})",
        f"setvz({init_vz})",
    ):
        parsers.execute_string(ctx, command)

    absolute_yaw = float(rows[0]["yaw"])
    for slot_index, slot in enumerate(slots[1:], start=1):
        row = rows[slot_index]
        absolute_yaw += float(row["yaw"])
        controls = slot["controls"]
        ctx.args = {
            "forward": fl(controls.get("forward", 0)),
            "strafe": fl(controls.get("strafe", 0)),
            "sprinting": bool(controls.get("sprint", False)),
            "sneaking": bool(controls.get("sneak", False)),
            "jumping": bool(controls.get("jump", False)),
            "airborne": slot["acceleration"]["medium"] == "air",
            "water": slot["acceleration"]["medium"] == "water",
            "lava": slot["acceleration"]["medium"] == "lava",
            "ladder": bool(slot.get("ladder", False)),
            "web": bool(slot.get("web", False)),
            "rotation": fl(absolute_yaw),
            "function_offset": fl(0),
        }
        retention = slot["retention"]["medium"]
        if retention == "flat_ground":
            ctx.args["slip"] = fl(0.6)
        elif retention == "slime":
            ctx.args["slip"] = fl(0.8)
        elif retention == "ice":
            ctx.args["slip"] = fl(0.98)

        player.move(ctx)
        state = states[slot_index + 1]

        assert player.x + player.vx == float(state["position"]["x"])
        assert player.z + player.vz == float(state["position"]["z"])
        assert player.vx == float(state["velocity"]["x"])
        assert player.vz == float(state["velocity"]["z"])
