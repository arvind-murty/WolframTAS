"""Parse mothball command strings (e.g. ``sj(12)``) into a WolframTAS
exact-solver input, and expose mothball's own simulated final state.

This drives the vendored mothball engine (orchestrator/vendor) as both the
command parser and the reference simulator. The per-tick ``move()`` arguments
(which carry medium/airborne info that ``input_history`` omits) are captured and
mapped to ``movement_plan`` slots. Original WolframTAS code; the engine it calls
is mothball's, vendored with permission (see orchestrator/vendor/NOTICE.md).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

_VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))


def _ground_retention_medium(slip: float) -> str:
    # mothball ground slipperiness -> WolframTAS retention medium.
    if abs(slip - 0.6) < 1e-6:
        return "flat_ground"
    if abs(slip - 0.8) < 1e-6:
        return "slime"
    if abs(slip - 0.98) < 1e-6:
        return "ice"
    raise ValueError(f"unsupported ground slipperiness: {slip}")


def _parse_wall_modifier(modifier: str) -> tuple[str, float] | None:
    """Parse a WolframTAS wall-collision modifier ``hitx=<v>`` / ``hitz=<v>``
    (e.g. ``s[hitz=5.0](1)``) into ``(axis, value)``, or None if not one."""
    for name, axis in (("hitx", "x"), ("hitz", "z")):
        if modifier.startswith(name + "="):
            return axis, float(modifier[len(name) + 1:])
    return None


def _split_wall_modifier(mods: list[str]) -> tuple[tuple[str, float] | None, list[str]]:
    """Separate a wall modifier from the mothball modifiers in a command's mods."""
    wall: tuple[str, float] | None = None
    clean: list[str] = []
    for modifier in mods:
        parsed = _parse_wall_modifier(modifier)
        if parsed is not None:
            wall = parsed
        else:
            clean.append(modifier)
    return wall, clean


def _slot_from_move_args(slot_index: int, args: dict, facing_deg: float, slip: float) -> dict:
    forward = int(round(float(args.get("forward", 0))))
    strafe = int(round(float(args.get("strafe", 0))))
    sprint = bool(args.get("sprinting", False))
    sneak = bool(args.get("sneaking", False))
    jump = bool(args.get("jumping", False))
    water = bool(args.get("water", False))
    lava = bool(args.get("lava", False))
    airborne = bool(args.get("airborne", False))

    if water:
        medium = "water"
        retention = "water"
    elif lava:
        medium = "lava"
        retention = "lava"
    elif airborne:
        medium = "air"
        retention = "air"
    else:
        medium = "ground"
        retention = _ground_retention_medium(slip)

    input_mode = "forward_45" if strafe != 0 else "no45_forward"

    # The contract angle is the movement (resultant) direction; the solver
    # re-derives the facing as -movement_direction + atan2(strafe, forward).
    # facing_deg is mothball's EFFECTIVE facing (MC yaw) for the tick, including
    # the 45-command function_offset and any rotation_offset; invert it here.
    facing_rad = math.radians(facing_deg)
    local = math.atan2(strafe, forward) if (forward or strafe) else 0.0
    movement_direction = local - facing_rad

    slot = {
        "slot": slot_index,
        "kind": "movement",
        "controls": {
            "forward": forward,
            "strafe": strafe,
            "jump": jump,
            "sneak": sneak,
            "sprint": sprint,
        },
        "acceleration": {"medium": medium, "input": input_mode},
        "retention": {"medium": retention},
        "_movement_direction": movement_direction,
    }
    if bool(args.get("web", False)):
        slot["web"] = True
    if bool(args.get("ladder", False)):
        slot["ladder"] = True
    return slot


def parse_command(command: str) -> dict[str, Any]:
    """Parse a mothball command string and return both a WolframTAS exact-solver
    input and mothball's own final simulated state.

    Returns a dict with keys ``exact_input`` (the solver input) and
    ``mothball_final`` (x, z, vx, vz from mothball's player).
    """
    slots, directions, mothball_final, has_wall = _simulate_command(command)
    n = len(slots)
    exact_input = {
        "version": 1,
        "name": f"command:{command}",
        "slot_indexing": "1_based",
        "n": n,
        "angle_domain": {"table_size": 65536},
        "initial_state": _initial_state(),
        "movement_plan": {"version": 1, "slot_indexing": "1_based", "slots": slots},
        "optimal_solution": {
            "status": "optimal",
            "objective_value": 0.0,
            "movement_directions": directions,
        },
    }
    # has_wall signals the comparison harness that mothball's reference used a
    # catch-up stop (so its final state aligns with the solver's actual last
    # state states[n], retained velocity), not the usual one-behind states[n-1].
    return {"exact_input": exact_input, "mothball_final": mothball_final, "wall_hit": has_wall}


def command_to_exact_template(command: str, objective_axis: str = "z", sense: str = "maximize") -> dict[str, Any]:
    """Parse a mothball command into a WolframTAS exact-solver *template* for the
    staged optimization flow: the movement_plan skeleton (per-tick keys/mediums)
    plus an objective, with the per-tick facing/angles left FREE for Mathematica
    to optimize (no fixed optimal_solution). The objective defaults to maximizing
    the final position along the given axis (z = travel-distance).
    """
    slots, _directions, _mothball_final, _has_wall = _simulate_command(command)
    n = len(slots)
    return {
        "version": 1,
        "name": f"command:{command}",
        "slot_indexing": "1_based",
        "n": n,
        "angle_domain": {"table_size": 65536},
        "initial_state": _initial_state(),
        "movement_plan": {"version": 1, "slot_indexing": "1_based", "slots": slots},
        "exact_objective": {"type": "position", "axis": objective_axis, "slot": n, "sense": sense},
        "constraints": [],
    }


def _initial_state() -> dict[str, Any]:
    return {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        "yaw": 0.0,
        "pitch": 0.0,
        "on_ground": True,
    }


def _simulate_command(command: str) -> tuple[list[dict], list[dict], dict[str, float], bool]:
    """Run the vendored mothball engine on a command, returning the movement_plan
    slots (with a leading zero-speed init slot for bookkeeping), the per-tick
    movement directions, mothball's final (x, z, vx, vz), and whether the command
    contained a wall-collision modifier.

    Inputless "stop" ticks are just mothball's ``stop`` / ``stopair`` commands
    (aliases ``st`` / ``sta``); they need no special handling here.

    Wall-collision modifiers ``hitx=<v>`` / ``hitz=<v>`` mark a tick that crosses
    a wall on an axis: the solver clamps the position to the wall, zeroes that
    axis's velocity, and drops sprint. mothball has no collision, so we exploit
    the fact that the post-collision state is exactly (pos=v, axis-velocity=0)
    regardless of the hit tick's movement: we hand mothball that state directly
    via setpos/setvel instead of simulating the hit, and append ONE catch-up stop
    so mothball's move-then-accelerate order settles the post-wall acceleration
    into position (matching the solver's accelerate-then-move). See parse_command
    for the resulting comparison alignment."""
    from cogs.movement.player import Player
    from cogs.movement.context import Context
    from cogs.movement import parsers

    tuples = parsers.string_to_args(command)
    has_wall = any(_split_wall_modifier(mods)[0] is not None for _, mods, _ in tuples)

    captured: list[tuple[dict, float, float]] = []
    tick_wall: dict[int, tuple[str, float]] = {}
    original_move = Player.move

    def spy(self, ctx):  # type: ignore[no-untyped-def]
        result = original_move(self, ctx)
        # Effective facing (MC yaw): last_rotation folds in the rotation arg /
        # default_rotation / rotation_offset; add the 45-command function_offset.
        facing = float(self.last_rotation) + float(ctx.args.get("function_offset", 0.0))
        # The slip the tick actually used (so setslip overrides are picked up).
        slip = float(self.prev_slip)
        captured.append((dict(ctx.args), facing, slip))
        return result

    # Pass A: run the command (wall modifiers stripped) to capture per-tick
    # params for the solver slots and mark which ticks carry a wall collision.
    player = Player()
    Player.move = spy
    last_airborne = False
    try:
        ctx = Context(player, [{}], False, "xz")
        for cmd, mods, args in tuples:
            wall, clean = _split_wall_modifier(mods)
            start = len(captured)
            parsers.execute_command(ctx, cmd, clean, args)
            if wall is not None:
                if len(captured) - start != 1:
                    raise ValueError("hitx=/hitz= requires a single-tick command")
                tick_wall[start] = wall
            if captured:
                last_airborne = bool(captured[-1][0].get("airborne", False))
    finally:
        Player.move = original_move

    # A leading zero-speed init slot absorbs mothball's one-tick position/velocity
    # bookkeeping offset, so states_exact[n-1] equals mothball's final position.
    slots: list[dict] = [{"slot": 1, "kind": "init", "speed": 0.0, "imux": 0.91, "imuz": 0.91}]
    directions = [{"slot": 1, "radians": 0.0, "degrees": 0.0}]
    for index, (args, facing_deg, slip) in enumerate(captured):
        slot_index = index + 2
        slot = _slot_from_move_args(slot_index, args, facing_deg, slip)
        if index in tick_wall:
            axis, value = tick_wall[index]
            slot["wall_collision"] = {"axis": axis, "value": value}
        md = slot.pop("_movement_direction")
        slots.append(slot)
        directions.append({"slot": slot_index, "radians": md, "degrees": math.degrees(md)})

    if not has_wall:
        mothball_final = {
            "x": float(player.x),
            "z": float(player.z),
            "vx": float(player.vx),
            "vz": float(player.vz),
        }
        return slots, directions, mothball_final, False

    # Pass B: mothball reference. Replace each hit tick with a direct set of the
    # post-collision state (the clamp result), run everything else normally, then
    # append one catch-up stop so the deferred post-wall acceleration settles.
    ref = Player()
    ref_ctx = Context(ref, [{}], False, "xz")
    for cmd, mods, args in tuples:
        wall, clean = _split_wall_modifier(mods)
        if wall is not None:
            axis, value = wall
            pos_cmd, vel_cmd = ("setposx", "setvx") if axis == "x" else ("setposz", "setvz")
            parsers.execute_command(ref_ctx, pos_cmd, [], [repr(value)])
            parsers.execute_command(ref_ctx, vel_cmd, [], ["0"])
        else:
            parsers.execute_command(ref_ctx, cmd, clean, args)
    parsers.execute_command(ref_ctx, "sta" if last_airborne else "st", [], ["1"])
    mothball_final = {
        "x": float(ref.x),
        "z": float(ref.z),
        "vx": float(ref.vx),
        "vz": float(ref.vz),
    }
    return slots, directions, mothball_final, True
