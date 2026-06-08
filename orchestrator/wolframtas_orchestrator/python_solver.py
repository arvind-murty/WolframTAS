"""Python exact solver: drives mothball's Player.move() directly for bit-exact
Minecraft parity. Mothball is the source of truth.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any, NamedTuple

_VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from numpy import float32 as fl  # noqa: E402

_CONSTANTS_PATH = Path(__file__).resolve().parent / "movement_constants.json"
with _CONSTANTS_PATH.open() as _f:
    _C = json.load(_f)

_SLIP: dict[str, float] = {"flat_ground": 0.6, "slime": 0.8, "ice": 0.98}
_RETENTION: dict[str, float] = _C["retention"]
_BASE: dict[str, float] = _C["base_movement"]


# ---------------------------------------------------------------------------
# Angle helpers
# ---------------------------------------------------------------------------
def _mc_angle_index(radians_f32: float) -> int:
    return int(fl(radians_f32) * fl(10430.378)) & 65535


def _index_to_degrees(k: int) -> float:
    return (k & 65535) * 360.0 / 65536.0


def _yaw_index_for_facing(facing_deg: float) -> int:
    return _mc_angle_index(float(fl(facing_deg * math.pi / 180.0)))


def _macro_absolute_yaw(yaw_idx: int) -> float:
    return (yaw_idx + 0.5) * 360.0 / 65536.0


def _facing_deg_from_slot(slot: dict, mv_rad: float) -> float:
    """Facing angle in degrees from a slot's movement direction (Mathematica)."""
    mv_rad_norm = math.remainder(mv_rad, 2.0 * math.pi)
    kind = slot.get("kind", "movement")
    if kind == "init":
        return -math.degrees(mv_rad_norm)
    fwd = int(slot["controls"]["forward"])
    str_ = int(slot["controls"]["strafe"])
    offset = math.degrees(math.atan2(str_, fwd)) if (fwd or str_) else 0.0
    return -math.degrees(mv_rad_norm) + offset


def _seed_yaw_indices(slots: list[dict], dirs: dict[int, float]) -> list[int]:
    """Compute the initial yaw_indices from Mathematica movement directions."""
    indices = []
    for slot in slots:
        slot_num = int(slot["slot"])
        mv_rad = dirs.get(slot_num, 0.0)
        indices.append(_yaw_index_for_facing(_facing_deg_from_slot(slot, mv_rad)))
    return indices


# ---------------------------------------------------------------------------
# Raw simulation (floats, not strings — used by repair inner loop)
# ---------------------------------------------------------------------------
class _RawState(NamedTuple):
    x: float            # Minecraft position (player.x + player.vx after slot)
    z: float
    vx: float           # player.vx after move() — retained+inputs, used for output/check
    vz: float
    retained_vx: float  # position_delta * retention — for inertia event checks
    retained_vz: float


def _simulate_raw(
    exact_input: dict[str, Any],
    yaw_indices: list[int],
    seed_indices: list[int],
) -> list[_RawState]:
    """Simulate and return raw float states, one per tick (0 = initial, 1..n = slots).

    For slots where yaw_indices[i] == seed_indices[i] (unrepaired): mothball
    receives the continuous Mathematica facing angle for maximum accuracy.
    For repaired slots: mothball receives the midpoint of the yaw bucket.
    """
    from cogs.movement.player import Player
    from cogs.movement.context import Context

    slots: list[dict] = exact_input["movement_plan"]["slots"]
    dirs: dict[int, float] = {
        d["slot"]: float(d["radians"])
        for d in exact_input["optimal_solution"]["movement_directions"]
    }
    init_state: dict = exact_input.get("initial_state", {})

    player = Player()
    player.x = float(init_state.get("position", {}).get("x", 0.0))
    player.z = float(init_state.get("position", {}).get("z", 0.0))
    player.vx = float(init_state.get("velocity", {}).get("x", 0.0))
    player.vz = float(init_state.get("velocity", {}).get("z", 0.0))

    raw: list[_RawState] = [_RawState(player.x, player.z, player.vx, player.vz, player.vx, player.vz)]
    force_unsprint_next = False
    virtual_x = player.x
    virtual_z = player.z

    for i, slot in enumerate(slots):
        slot_num = int(slot["slot"])
        mv_rad = dirs.get(slot_num, 0.0)
        kind = slot.get("kind", "movement")
        yaw_idx = yaw_indices[i]
        seed_idx = seed_indices[i]

        if kind == "init":
            speed = float(slot.get("speed", 0.0))
            imux = float(slot.get("imux", _RETENTION["flat_ground"]))
            imuz = float(slot.get("imuz", _RETENTION["flat_ground"]))
            mv_rad_norm = math.remainder(mv_rad, 2.0 * math.pi)
            dvx = math.sin(mv_rad_norm) * speed
            dvz = math.cos(mv_rad_norm) * speed
            player.vx += dvx
            player.vz += dvz
            slip = imux / 0.91 if imux > 0.0 else 0.6
            player.prev_slip = fl(slip)
            raw.append(_RawState(
                player.x + player.vx, player.z + player.vz,
                player.vx, player.vz,
                player.vx * imux, player.vz * imuz,
            ))
            continue

        fwd = int(slot["controls"]["forward"])
        str_ = int(slot["controls"]["strafe"])
        sprint = bool(slot["controls"]["sprint"])
        sneak = bool(slot["controls"]["sneak"])
        jump = bool(slot["controls"]["jump"])
        if force_unsprint_next:
            sprint = False
            force_unsprint_next = False

        accel_medium = slot["acceleration"]["medium"]
        ret_medium = slot["retention"]["medium"]
        wall_hit_axes = slot.get("wall_hit", {}).get("axes", [])
        ladder = bool(slot.get("ladder", False))
        web = bool(slot.get("web", False))

        # Facing: use Mathematica angle for unrepaired, bucket midpoint for repaired
        if yaw_idx == seed_idx:
            facing_deg = _facing_deg_from_slot(slot, mv_rad)
        else:
            facing_deg = _macro_absolute_yaw(yaw_idx)

        args: dict[str, Any] = {
            "forward": fl(fwd), "strafe": fl(str_),
            "sprinting": sprint, "sneaking": sneak, "jumping": jump,
            "airborne": accel_medium == "air",
            "water": accel_medium == "water",
            "lava": accel_medium == "lava",
            "ladder": ladder, "web": web,
            "rotation": fl(facing_deg), "function_offset": fl(0),
        }
        if ret_medium in _SLIP:
            args["slip"] = fl(_SLIP[ret_medium])

        x_before = player.x
        z_before = player.z
        vx_before_virtual = virtual_x
        vz_before_virtual = virtual_z

        ctx = Context(player, [{}], False, "xz")
        ctx.args = args
        player.move(ctx)

        virtual_x += player.vx
        virtual_z += player.vz

        retention = _RETENTION.get(ret_medium, _RETENTION["air"])
        move_vx = player.x - x_before  # = V[m], the velocity used in pos += vel
        move_vz = player.z - z_before

        # wall_hit: zero blocked axis (retained_v = 0 on that axis)
        if "x" in wall_hit_axes:
            player.vx = 0.0
            virtual_x = vx_before_virtual
        if "z" in wall_hit_axes:
            player.vz = 0.0
            virtual_z = vz_before_virtual

        ret_vx = 0.0 if "x" in wall_hit_axes else move_vx * retention
        ret_vz = 0.0 if "z" in wall_hit_axes else move_vz * retention

        # wall_collision: threshold clamp
        wall_col = slot.get("wall_collision")
        if wall_col:
            axis = wall_col["axis"]
            val = float(wall_col["value"])
            if axis == "x":
                if (vx_before_virtual < val <= virtual_x) or (vx_before_virtual > val >= virtual_x):
                    player.x = val; player.vx = 0.0; virtual_x = val
                    ret_vx = 0.0; force_unsprint_next = True
            elif axis == "z":
                if (vz_before_virtual < val <= virtual_z) or (vz_before_virtual > val >= virtual_z):
                    player.z = val; player.vz = 0.0; virtual_z = val
                    ret_vz = 0.0; force_unsprint_next = True

        raw.append(_RawState(
            player.x + player.vx, player.z + player.vz,
            player.vx, player.vz,
            ret_vx, ret_vz,
        ))

    return raw


# ---------------------------------------------------------------------------
# Constraint evaluation
# ---------------------------------------------------------------------------
class _Eval(NamedTuple):
    score: float
    residual_norm: float
    objective_value: float
    objective_deviation: float
    objective_residual: float
    feasible: bool
    worst_id: str
    worst_residual: float


def _evaluate(
    raw: list[_RawState],
    exact_input: dict[str, Any],
    yaw_indices: list[int],
    _dirs: dict[int, float] | None = None,
) -> _Eval:
    sq_sum = 0.0
    worst_id = ""
    worst_res = 0.0

    def _add(cid: str, residual: float) -> None:
        nonlocal sq_sum, worst_id, worst_res
        if residual <= 0.0:
            return
        sq_sum += residual * residual
        if residual > worst_res:
            worst_res = residual
            worst_id = cid

    def _pos(state: _RawState, axis: str) -> float:
        return state.x if axis == "x" else state.z

    for c in exact_input.get("constraints", []):
        cid = c["id"]
        tol = float(c.get("exact_tolerance", 0.0))
        ctype = c["type"]

        if ctype == "position_bounds":
            s = raw[int(c["slot"])]
            if "min_x" in c: _add(cid, float(c["min_x"]) - s.x - tol)
            if "max_x" in c: _add(cid, s.x - float(c["max_x"]) - tol)
            if "min_z" in c: _add(cid, float(c["min_z"]) - s.z - tol)
            if "max_z" in c: _add(cid, s.z - float(c["max_z"]) - tol)

        elif ctype == "position_delta_bound":
            axis = c["axis"]
            lhs = _pos(raw[int(c["lhs_slot"])], axis)
            rhs = _pos(raw[int(c["rhs_slot"])], axis)
            delta = lhs - rhs
            val = float(c["value"])
            if c["sense"] == ">=":
                _add(cid, val - delta - tol)
            else:
                _add(cid, delta - val - tol)

        elif ctype == "position_delta_offset_bound":
            axis = c["axis"]
            lhs = _pos(raw[int(c["lhs_slot"])], axis)
            rhs = _pos(raw[int(c["rhs_slot"])], axis)
            delta = lhs - rhs
            off = float(c.get("offset_value", 0.0))
            if c["sense"] == ">=":
                _add(cid, off - delta - tol)
            else:
                _add(cid, delta - off - tol)

        elif ctype == "facing_degrees_equal":
            slot_i = int(c["slot"]) - 1  # 0-based index into yaw_indices
            if slot_i < len(yaw_indices):
                slots = exact_input["movement_plan"]["slots"]
                is_init = slot_i < len(slots) and slots[slot_i].get("kind") == "init"
                if is_init and _dirs is not None:
                    # Init slots use the exact Mathematica movement direction
                    slot_num = int(slots[slot_i]["slot"])
                    mv_rad = math.remainder(_dirs.get(slot_num, 0.0), 2.0 * math.pi)
                    mv_dir_rad = mv_rad
                else:
                    mv_dir_rad = -_index_to_degrees(yaw_indices[slot_i]) * math.pi / 180.0
                target_rad = float(c["degrees"]) * math.pi / 180.0
                err = abs(math.remainder(mv_dir_rad - target_rad, 2.0 * math.pi))
                tol_rad = float(c.get("exact_tolerance_degrees", 0.0)) * math.pi / 180.0
                _add(cid, err - tol_rad)

    for ev in exact_input.get("inertia_events", []):
        eid = ev["id"]
        slot = int(ev["slot"])
        axis = ev["axis"]
        threshold = float(ev.get("threshold", 0.005))
        state = raw[slot]
        velocity = state.retained_vx if axis == "x" else state.retained_vz

        if ev["type"] == "hit":
            _add(eid, abs(velocity) - threshold)
        elif ev.get("direction") == "positive":
            _add(eid, threshold - velocity)
        elif ev.get("direction") == "negative":
            _add(eid, threshold + velocity)

    residual_norm = math.sqrt(sq_sum)

    obj = exact_input.get("exact_objective", {})
    obj_val = 0.0
    obj_dev = 0.0
    obj_res = 0.0
    if obj.get("type") == "position":
        obj_slot = int(obj.get("slot", len(raw) - 1))
        obj_axis = obj.get("axis", "z")
        obj_val = _pos(raw[obj_slot], obj_axis) if obj_slot < len(raw) else 0.0
        target = float(obj.get("target_value", obj_val))
        sol_tol = float(obj.get("solution_tolerance", 0.001))
        obj_dev = abs(obj_val - target)
        obj_res = max(0.0, obj_dev - sol_tol)

    score = residual_norm + obj_res
    return _Eval(score, residual_norm, obj_val, obj_dev, obj_res,
                 score == 0.0, worst_id, worst_res)


# ---------------------------------------------------------------------------
# Repair search
# ---------------------------------------------------------------------------
def _repair(
    exact_input: dict[str, Any],
    seed_indices: list[int],
    dirs: dict[int, float],
) -> tuple[list[int], dict[str, Any]]:
    cfg = exact_input.get("exact_solver", {})
    max_iter = int(cfg.get("max_repair_iterations", 8))
    max_evals = int(cfg.get("max_candidate_evaluations", 2000))
    top_k = int(cfg.get("top_k_moves", 8))
    max_delta = max(1, int(cfg.get("max_index_delta_per_iteration", 2)))

    slots = exact_input["movement_plan"]["slots"]
    movable = [i for i, s in enumerate(slots) if s.get("kind", "movement") != "init"]

    best = list(seed_indices)
    best_raw = _simulate_raw(exact_input, best, seed_indices)
    initial_ev = _evaluate(best_raw, exact_input, best, dirs)
    best_ev = initial_ev
    evals = 0
    iters = 0

    if best_ev.feasible:
        return best, _diag(initial_ev, best_ev, 0, 0, seed_indices, best)

    for _ in range(max_iter):
        iters += 1
        base_score = best_ev.score

        # Scan ±delta on each movable slot
        ranked: list[tuple[float, int, int, int]] = []  # (score, |delta|, slot_i, delta)
        for i in movable:
            for d in range(1, max_delta + 1):
                for sign in (-1, +1):
                    if evals >= max_evals:
                        break
                    cand = list(best)
                    cand[i] = (cand[i] + sign * d) & 65535
                    ev = _evaluate(_simulate_raw(exact_input, cand, seed_indices), exact_input, cand, dirs)
                    evals += 1
                    if ev.score < base_score:
                        ranked.append((ev.score, d, i, sign * d))

        commit = list(best)
        commit_ev_box = [best_ev]

        def _try(moves: list[tuple]) -> None:
            nonlocal evals
            if evals >= max_evals:
                return
            cand = list(best)
            for _, _, si, di in moves:
                cand[si] = (cand[si] + di) & 65535
            ev = _evaluate(_simulate_raw(exact_input, cand, seed_indices), exact_input, cand, dirs)
            evals += 1
            if ev.score < commit_ev_box[0].score:
                commit[:] = cand
                commit_ev_box[0] = ev

        if ranked:
            ranked.sort()
            top = ranked[:top_k]
            for m in top:
                _try([m])
            for a, b in itertools.combinations(range(len(top)), 2):
                if top[a][2] != top[b][2]:
                    _try([top[a], top[b]])
            for a, b, c in itertools.combinations(range(len(top)), 3):
                ia, ib, ic = top[a][2], top[b][2], top[c][2]
                if ia != ib and ia != ic and ib != ic:
                    _try([top[a], top[b], top[c]])
        else:
            # Exhaustive ±1 pair fallback when no individual move helps
            all_unit = [(i, d) for i in movable for d in (-1, +1)]
            for ai in range(len(all_unit)):
                for bj in range(ai + 1, len(all_unit)):
                    if all_unit[ai][0] == all_unit[bj][0]:
                        continue  # same slot
                    if evals >= max_evals:
                        break
                    si, di = all_unit[ai]
                    sj, dj = all_unit[bj]
                    cand = list(best)
                    cand[si] = (cand[si] + di) & 65535
                    cand[sj] = (cand[sj] + dj) & 65535
                    ev = _evaluate(_simulate_raw(exact_input, cand, seed_indices), exact_input, cand, dirs)
                    evals += 1
                    if ev.score < commit_ev_box[0].score:
                        commit[:] = cand
                        commit_ev_box[0] = ev

        if commit_ev_box[0].score >= base_score:
            break
        best = list(commit)
        best_ev = commit_ev_box[0]
        if best_ev.feasible or evals >= max_evals:
            break

    return best, _diag(initial_ev, best_ev, iters, evals, seed_indices, best)


def _diag(
    initial: _Eval, final: _Eval,
    iters: int, evals: int,
    seed: list[int], best: list[int],
) -> dict[str, Any]:
    changed = [
        {"slot": i + 1, "from": seed[i], "to": best[i], "delta": (best[i] - seed[i] + 32768) & 65535 - 32768}
        for i in range(len(seed)) if seed[i] != best[i]
    ]
    return {
        "initial_residual_norm": str(initial.residual_norm),
        "final_residual_norm": str(final.residual_norm),
        "worst_constraint_id": final.worst_id,
        "candidate_evaluations": evals,
        "repair_iterations": iters,
        "exact_objective_value": str(final.objective_value),
        "objective_deviation": str(final.objective_deviation),
        "changed_angle_indices": changed,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def solve(exact_input: dict[str, Any]) -> dict[str, Any]:
    """Simulate and optionally repair angles to satisfy constraints."""
    slots: list[dict] = exact_input["movement_plan"]["slots"]
    dirs: dict[int, float] = {
        d["slot"]: float(d["radians"])
        for d in exact_input["optimal_solution"]["movement_directions"]
    }
    n = int(exact_input["n"])

    seed_indices = _seed_yaw_indices(slots, dirs)

    # Repair if there are constraints or an objective to satisfy
    has_work = bool(exact_input.get("constraints")) or bool(exact_input.get("inertia_events")) or bool(exact_input.get("exact_objective"))
    if has_work:
        best_indices, diag = _repair(exact_input, seed_indices, dirs)
    else:
        best_indices = list(seed_indices)
        diag = _diag(_Eval(0, 0, 0, 0, 0, True, "", 0), _Eval(0, 0, 0, 0, 0, True, "", 0), 0, 0, seed_indices, best_indices)

    # Final simulation for output
    final_raw = _simulate_raw(exact_input, best_indices, seed_indices)
    final_ev = _evaluate(final_raw, exact_input, best_indices, dirs)

    # Full simulation pass for macro rows and derived model arrays
    # (reuses the raw states but needs slot-level data for macro and imux/imuz/mmu)
    macro_rows, imux_arr, imuz_arr, mmu_arr, angles_discrete = _format_passes(
        slots, dirs, best_indices, seed_indices
    )

    obj = exact_input.get("exact_objective", {})
    obj_slot = int(obj.get("slot", n))
    obj_val = (final_raw[obj_slot].x if obj.get("axis") == "x" else final_raw[obj_slot].z) if obj_slot < len(final_raw) else 0.0

    states_exact = [
        _make_state(i, s.x, s.z, s.vx, s.vz, s.retained_vx, s.retained_vz)
        for i, s in enumerate(final_raw)
    ]

    return {
        "version": 1,
        "status": "solved" if final_ev.feasible else "failed",
        "angles_discrete": angles_discrete,
        "states_exact": states_exact,
        "macro_rows": macro_rows,
        "derived_model": {"imux": imux_arr, "imuz": imuz_arr, "mmu": mmu_arr},
        "diagnostics": {
            "mode": "python_solver",
            "state_count": len(states_exact),
            **diag,
        },
    }


def _format_passes(
    slots: list[dict],
    dirs: dict[int, float],
    best_indices: list[int],
    seed_indices: list[int],
) -> tuple[list[dict], list[float], list[float], list[float], list[dict]]:
    """Compute macro rows, derived model arrays, and angles_discrete."""
    macro_rows: list[dict] = []
    imux_arr: list[float] = []
    imuz_arr: list[float] = []
    mmu_arr: list[float] = []
    angles_discrete: list[dict] = []
    prev_abs_yaw = 0.0

    for i, slot in enumerate(slots):
        slot_num = int(slot["slot"])
        mv_rad = dirs.get(slot_num, 0.0)
        kind = slot.get("kind", "movement")
        yaw_idx = best_indices[i]

        angles_discrete.append({
            "tick": i,
            "yaw_index": yaw_idx,
            "pitch_index": 0,
            "yaw_degrees": _index_to_degrees(yaw_idx),
            "pitch_degrees": 0,
        })

        abs_yaw = _macro_absolute_yaw(yaw_idx) if kind != "init" else -math.degrees(math.remainder(mv_rad, 2 * math.pi))
        macro_rows.append(_make_macro_row(slot, abs_yaw - prev_abs_yaw))
        prev_abs_yaw = abs_yaw

        if kind == "init":
            imux_arr.append(float(slot.get("imux", _RETENTION["flat_ground"])))
            imuz_arr.append(float(slot.get("imuz", _RETENTION["flat_ground"])))
            mmu_arr.append(float(slot.get("speed", 0.0)))
        else:
            sprint = bool(slot["controls"]["sprint"])
            accel = slot["acceleration"]["medium"]
            ret = slot["retention"]["medium"]
            wall_axes = slot.get("wall_hit", {}).get("axes", [])
            imu_base = _RETENTION.get(ret, _RETENTION["air"])
            imux_arr.append(0.0 if "x" in wall_axes else imu_base)
            imuz_arr.append(0.0 if "z" in wall_axes else imu_base)
            if accel == "ground":
                key = f"ground_{ret}_{'sprint' if sprint else 'walk'}"
                mmu_arr.append(_BASE.get(key, _BASE["ground_flat_ground_walk"]))
            elif accel == "water":
                mmu_arr.append(_BASE["water"])
            elif accel == "lava":
                mmu_arr.append(_BASE["lava"])
            else:
                mmu_arr.append(_BASE["air_sprint"] if sprint else _BASE["air_walk"])

    return macro_rows, imux_arr, imuz_arr, mmu_arr, angles_discrete


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
        "w": fwd > 0, "a": str_ > 0, "s": fwd < 0, "d": str_ < 0,
        "p": bool(ctrl.get("sprint", False)),
        "n": bool(ctrl.get("sneak", False)),
        "j": bool(ctrl.get("jump", False)),
        "yaw": yaw_delta, "pitch": 0.0, "l": 0, "r": 0, "count": 1,
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
