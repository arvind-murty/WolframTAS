"""Python exact solver: drives mothball's Player.move() directly for bit-exact
Minecraft parity. Mothball is the source of truth; this replaces the C++ solver.
Angle repair is not yet implemented (angles come from optimal_solution as-is).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

_VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from numpy import float32 as fl  # noqa: E402

# Load movement constants from the committed JSON artifact
_CONSTANTS_PATH = Path(__file__).resolve().parent / "movement_constants.json"
with _CONSTANTS_PATH.open() as _f:
    _C = json.load(_f)

# ---------------------------------------------------------------------------
# Slip constants (ground retention medium → mothball slip value)
# ---------------------------------------------------------------------------
_SLIP: dict[str, float] = {
    "flat_ground": 0.6,
    "slime": 0.8,
    "ice": 0.98,
}

# Retention multipliers per medium (for derived_model output)
_RETENTION: dict[str, float] = _C["retention"]
_BASE: dict[str, float] = _C["base_movement"]


# ---------------------------------------------------------------------------
# Minecraft angle index helpers
# ---------------------------------------------------------------------------
def _mc_angle_index(radians_f32: float) -> int:
    return int(fl(radians_f32) * fl(10430.378)) & 65535


def _index_to_degrees(k: int) -> float:
    return (k & 65535) * 360.0 / 65536.0


def _yaw_index_for_facing(facing_deg: float) -> int:
    return _mc_angle_index(float(fl(facing_deg * math.pi / 180.0)))


def _macro_absolute_yaw(yaw_idx: int) -> float:
    """Midpoint of the angle bucket — maximises float32 tolerance in-game."""
    return (yaw_idx + 0.5) * 360.0 / 65536.0


# ---------------------------------------------------------------------------
# Main solver entry point
# ---------------------------------------------------------------------------
def solve(exact_input: dict[str, Any]) -> dict[str, Any]:
    """Simulate the trajectory described by *exact_input* using mothball and
    return an exact-solution dict in the same schema as the C++ solver."""
    from cogs.movement.player import Player
    from cogs.movement.context import Context

    slots: list[dict] = exact_input["movement_plan"]["slots"]
    dirs: dict[int, float] = {
        d["slot"]: float(d["radians"])
        for d in exact_input["optimal_solution"]["movement_directions"]
    }
    init_state: dict = exact_input.get("initial_state", {})
    n: int = int(exact_input["n"])

    player = Player()
    player.x = float(init_state.get("position", {}).get("x", 0.0))
    player.z = float(init_state.get("position", {}).get("z", 0.0))
    player.vx = float(init_state.get("velocity", {}).get("x", 0.0))
    player.vz = float(init_state.get("velocity", {}).get("z", 0.0))

    # states[0] = initial state before any processing
    states: list[dict] = [_make_state(0, player.x, player.z, 0.0, 0.0, player.vx, player.vz)]
    yaw_indices: list[int] = []
    prev_absolute_yaw: float = 0.0
    macro_rows: list[dict] = []
    imux_arr: list[float] = []
    imuz_arr: list[float] = []
    mmu_arr: list[float] = []

    force_unsprint_next: bool = False
    # Virtual accumulated position (matches command_parser's crossing check):
    # updated by adding player.vx/vz AFTER each move(), giving the Minecraft
    # position that wall-collision crossing is tested against.
    virtual_x: float = player.x
    virtual_z: float = player.z

    for slot in slots:
        slot_num: int = int(slot["slot"])
        kind: str = slot.get("kind", "movement")
        mv_rad: float = dirs.get(slot_num, 0.0)
        mv_rad_norm: float = math.remainder(mv_rad, 2.0 * math.pi)

        if kind == "init":
            speed = float(slot.get("speed", 0.0))
            imux = float(slot.get("imux", _RETENTION["flat_ground"]))
            imuz = float(slot.get("imuz", _RETENTION["flat_ground"]))

            dvx = math.sin(mv_rad_norm) * speed
            dvz = math.cos(mv_rad_norm) * speed
            player.vx += dvx
            player.vz += dvz

            # Set prev_slip so the next move() applies the right retention
            slip = imux / 0.91 if imux > 0.0 else 0.6
            player.prev_slip = fl(slip)

            imux_arr.append(imux)
            imuz_arr.append(imuz)
            mmu_arr.append(speed)

            facing_deg = -math.degrees(mv_rad_norm)
            yaw_idx = _yaw_index_for_facing(facing_deg)
            yaw_indices.append(yaw_idx)

            abs_yaw = _macro_absolute_yaw(yaw_idx)
            macro_rows.append(_make_macro_row(slot, abs_yaw - prev_absolute_yaw))
            prev_absolute_yaw = abs_yaw

            # Position includes the vx/vz that will move position in the next tick
            states.append(_make_state(
                slot_num,
                player.x + player.vx, player.z + player.vz,
                player.vx, player.vz,
                player.vx * imux, player.vz * imuz,
            ))
            continue

        # --- movement slot ---
        fwd = int(slot["controls"]["forward"])
        str_ = int(slot["controls"]["strafe"])
        sprint = bool(slot["controls"]["sprint"])
        sneak = bool(slot["controls"]["sneak"])
        jump = bool(slot["controls"]["jump"])

        if force_unsprint_next:
            sprint = False
            force_unsprint_next = False

        accel_medium: str = slot["acceleration"]["medium"]
        ret_medium: str = slot["retention"]["medium"]
        wall_hit: dict = slot.get("wall_hit", {})
        wall_hit_axes: list = wall_hit.get("axes", [])
        ladder: bool = bool(slot.get("ladder", False))
        web: bool = bool(slot.get("web", False))

        # Facing angle from movement direction + strafe/forward offset
        facing_offset_deg = math.degrees(math.atan2(str_, fwd)) if (fwd or str_) else 0.0
        facing_deg = -math.degrees(mv_rad_norm) + facing_offset_deg

        yaw_idx = _yaw_index_for_facing(facing_deg)
        yaw_indices.append(yaw_idx)

        # Retention for derived_model
        imu_base = _RETENTION.get(ret_medium, _RETENTION["air"])
        imux_val = 0.0 if "x" in wall_hit_axes else imu_base
        imuz_val = 0.0 if "z" in wall_hit_axes else imu_base

        # mmu approximation for derived_model (not used in actual physics)
        if accel_medium == "ground":
            key = f"ground_{ret_medium}_{'sprint' if sprint else 'walk'}"
            mmu_base = _BASE.get(key, _BASE["ground_flat_ground_walk"])
        elif accel_medium == "water":
            mmu_base = _BASE["water"]
        elif accel_medium == "lava":
            mmu_base = _BASE["lava"]
        else:  # air
            mmu_base = _BASE["air_sprint"] if sprint else _BASE["air_walk"]

        imux_arr.append(imux_val)
        imuz_arr.append(imuz_val)
        mmu_arr.append(mmu_base)

        # Build mothball args
        args: dict[str, Any] = {
            "forward": fl(fwd),
            "strafe": fl(str_),
            "sprinting": sprint,
            "sneaking": sneak,
            "jumping": jump,
            "airborne": accel_medium == "air",
            "water": accel_medium == "water",
            "lava": accel_medium == "lava",
            "ladder": ladder,
            "web": web,
            "rotation": fl(facing_deg),
            "function_offset": fl(0),
        }
        if ret_medium in _SLIP:
            args["slip"] = fl(_SLIP[ret_medium])

        vx_before_virtual = virtual_x
        vz_before_virtual = virtual_z

        ctx = Context(player, [{}], False, "xz")
        ctx.args = args
        player.move(ctx)

        # Update virtual position using post-move vx/vz (matches command_parser spy)
        virtual_x += player.vx
        virtual_z += player.vz

        # wall_hit.axes: zero blocked axis velocity (retention-only wall model)
        if "x" in wall_hit_axes:
            player.vx = 0.0
            virtual_x = vx_before_virtual  # crossing didn't move player
        if "z" in wall_hit_axes:
            player.vz = 0.0
            virtual_z = vz_before_virtual

        # wall_collision: threshold position clamp (hitx/hitz)
        # Crossing is detected against the virtual (Minecraft) position, not
        # player.z which is one tick behind.
        wall_col = slot.get("wall_collision")
        if wall_col:
            axis = wall_col["axis"]
            val = float(wall_col["value"])
            if axis == "x":
                crossed = (vx_before_virtual < val <= virtual_x) or (vx_before_virtual > val >= virtual_x)
                if crossed:
                    player.x = val
                    player.vx = 0.0
                    virtual_x = val
                    force_unsprint_next = True
            elif axis == "z":
                crossed = (vz_before_virtual < val <= virtual_z) or (vz_before_virtual > val >= virtual_z)
                if crossed:
                    player.z = val
                    player.vz = 0.0
                    virtual_z = val
                    force_unsprint_next = True

        abs_yaw = _macro_absolute_yaw(yaw_idx)
        macro_rows.append(_make_macro_row(slot, abs_yaw - prev_absolute_yaw))
        prev_absolute_yaw = abs_yaw

        states.append(_make_state(
            slot_num,
            player.x + player.vx, player.z + player.vz,
            player.vx, player.vz,
            player.vx, player.vz,
        ))

    angles_discrete = [
        {
            "tick": i,
            "yaw_index": yaw_indices[i],
            "pitch_index": 0,
            "yaw_degrees": _index_to_degrees(yaw_indices[i]),
            "pitch_degrees": 0,
        }
        for i in range(len(yaw_indices))
    ]

    obj = exact_input.get("exact_objective", {})
    obj_axis = obj.get("axis", "z")
    obj_slot = int(obj.get("slot", n))
    obj_val = float(states[obj_slot]["position"][obj_axis]) if obj_slot < len(states) else 0.0

    return {
        "version": 1,
        "status": "solved",
        "angles_discrete": angles_discrete,
        "states_exact": states,
        "macro_rows": macro_rows,
        "derived_model": {"imux": imux_arr, "imuz": imuz_arr, "mmu": mmu_arr},
        "diagnostics": {
            "mode": "python_solver",
            "state_count": len(states),
            "initial_residual_norm": "0",
            "final_residual_norm": "0",
            "worst_constraint_id": "",
            "candidate_evaluations": 0,
            "repair_iterations": 0,
            "exact_objective_value": str(obj_val),
            "objective_deviation": "0",
            "changed_angle_indices": [],
        },
    }


def _make_state(
    tick: int,
    pos_x: float, pos_z: float,
    move_vx: float, move_vz: float,
    retained_vx: float, retained_vz: float,
) -> dict:
    return {
        "tick": tick,
        "position": {"x": str(pos_x), "y": "0", "z": str(pos_z)},
        "velocity": {"x": str(move_vx), "y": "0", "z": str(move_vz)},
        "retained_velocity": {"x": str(retained_vx), "z": str(retained_vz)},
        "on_ground": False,
    }


def _make_macro_row(slot: dict, yaw_delta: float) -> dict:
    ctrl = slot.get("controls", {})
    fwd = int(ctrl.get("forward", 0))
    str_ = int(ctrl.get("strafe", 0))
    return {
        "w": fwd > 0,
        "a": str_ > 0,
        "s": fwd < 0,
        "d": str_ < 0,
        "p": bool(ctrl.get("sprint", False)),
        "n": bool(ctrl.get("sneak", False)),
        "j": bool(ctrl.get("jump", False)),
        "yaw": yaw_delta,
        "pitch": 0.0,
        "l": 0,
        "r": 0,
        "count": 1,
    }


def write_macro_csv(out_path: Path, solution: dict[str, Any]) -> None:
    lines = ["W,A,S,D,P,N,J,YAW,PITCH,L,R,COUNT"]
    for r in solution["macro_rows"]:
        lines.append(
            f"{'true' if r['w'] else 'false'},"
            f"{'true' if r['a'] else 'false'},"
            f"{'true' if r['s'] else 'false'},"
            f"{'true' if r['d'] else 'false'},"
            f"{'true' if r['p'] else 'false'},"
            f"{'true' if r['n'] else 'false'},"
            f"{'true' if r['j'] else 'false'},"
            f"{r['yaw']},{r['pitch']},{r['l']},{r['r']},{r['count']}"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
