from __future__ import annotations

import copy
import itertools
import re
from typing import Any

from .movement_model import retention_for
from .vertical_model import jump_air_ticks, vertical_trace

PLAYER_HALF_WIDTH = 0.3
PLAYER_HEIGHT = 1.8
SIDE_ORDER = ("west", "east", "north", "south")
TRANSITION_SIDE_PAIRS = tuple((a, b) for a in SIDE_ORDER for b in SIDE_ORDER if a != b)
TWO_CORNER_SIDE_TRIPLES = (
    ("north", "west", "south"),
    ("south", "west", "north"),
    ("north", "east", "south"),
    ("south", "east", "north"),
    ("west", "north", "east"),
    ("east", "north", "west"),
    ("west", "south", "east"),
    ("east", "south", "west"),
)


def block_route_to_exact_template(route: dict[str, Any]) -> dict[str, Any]:
    bundle = block_route_to_candidate_bundle(route)
    if bundle["kind"] == "exact_template":
        return bundle["exact_template"]
    raise ValueError("block route with avoid_blocks produces multiple candidates; use block_route_to_candidate_bundle")


def block_route_to_candidate_bundle(route: dict[str, Any]) -> dict[str, Any]:
    blocks = _route_landing_blocks(route)

    defaults = route.get("defaults", {})
    default_run_ticks = int(defaults.get("run_ticks", 0))
    if default_run_ticks < 0:
        raise ValueError("defaults.run_ticks must be >= 0")

    normalized_blocks = [_normalize_block(block, index, default_run_ticks) for index, block in enumerate(blocks)]
    if normalized_blocks[-1]["run_ticks"] != 0:
        raise ValueError("final block run_ticks must be 0 because there is no following jump")
    raw_avoid_blocks = route.get("avoid_blocks", [])
    if not isinstance(raw_avoid_blocks, list):
        raise ValueError("avoid_blocks must be a list")
    avoid_blocks = [_normalize_avoid_block(block, index) for index, block in enumerate(raw_avoid_blocks)]

    slots: list[dict[str, Any]] = [
        {
            "slot": 1,
            "kind": "init",
            "speed": float(route.get("init_speed", 0.0)),
            "imux": float(route.get("init_imux", retention_for("flat_ground"))),
            "imuz": float(route.get("init_imuz", retention_for("flat_ground"))),
        }
    ]
    base_constraints: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    segment_infos: list[dict[str, Any]] = []

    origin = normalized_blocks[0]
    slot_number = 1
    for index in range(len(normalized_blocks) - 1):
        departure = normalized_blocks[index]
        target = normalized_blocks[index + 1]

        for run_index in range(departure["run_ticks"]):
            slot_number += 1
            slots.append(_ground_sprint_slot(slot_number, jump=False))
            base_constraints.append(_position_bounds_constraint(
                f"run_{departure['id']}_tick_{slot_number}",
                slot_number,
                departure,
                origin,
                reason=f"run tick {run_index + 1} on {departure['id']}",
            ))

        slot_number += 1
        slots.append(_ground_sprint_slot(slot_number, jump=True))

        from_surface_y = _surface_y(departure)
        to_surface_y = _surface_y(target)
        air_ticks = jump_air_ticks(from_surface_y, to_surface_y)
        jump_slot = slot_number
        annotations.append({
            "kind": "block_route_segment",
            "from": departure["id"],
            "to": target["id"],
            "run_ticks": departure["run_ticks"],
            "jump_slot": jump_slot,
            "air_ticks": air_ticks,
        })
        segment_infos.append({
            "from": departure["id"],
            "to": target["id"],
            "from_surface_y": from_surface_y,
            "to_surface_y": to_surface_y,
            "jump_slot": jump_slot,
            "landing_slot": jump_slot + air_ticks,
            "air_ticks": air_ticks,
            "vertical_trace": vertical_trace(from_surface_y, to_surface_y),
        })
        for _ in range(air_ticks):
            slot_number += 1
            slots.append(_sprint_45_air_slot(slot_number))

        base_constraints.append(_position_bounds_constraint(
            f"land_{target['id']}_tick_{slot_number}",
            slot_number,
            target,
            origin,
            reason=f"landing on {target['id']}",
        ))

    objective = route.get("objective", {})
    axis = objective.get("axis", "z")
    if axis not in {"x", "z"}:
        raise ValueError("objective.axis must be 'x' or 'z'")
    sense = objective.get("sense", "maximize")
    if sense not in {"maximize", "minimize"}:
        raise ValueError("objective.sense must be 'maximize' or 'minimize'")
    function = "X" if axis == "x" else "Z"

    template: dict[str, Any] = {
        "version": 1,
        "name": route.get("name", "block_route"),
        "slot_indexing": "1_based",
        "n": slot_number,
        "angle_domain": {"table_size": 65536},
        "initial_state": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "yaw": float(route.get("initial_yaw", 0.0)),
            "pitch": float(route.get("initial_pitch", 0.0)),
            "on_ground": True,
        },
        "movement_plan": {
            "version": 1,
            "slot_indexing": "1_based",
            "slots": slots,
        },
        "exact_objective": {
            "type": "position",
            "axis": axis,
            "slot": int(objective.get("slot", slot_number)),
            "sense": sense,
            "expression": objective.get("expression", f"{function}[F,{int(objective.get('slot', slot_number))}]"),
        },
        "constraints": base_constraints,
        "annotations": [{
            "kind": "block_route",
            "origin_block": origin["id"],
            "landing_blocks": copy.deepcopy(normalized_blocks),
            "avoid_blocks": copy.deepcopy(avoid_blocks),
        }, *annotations],
    }

    for key in ("solver", "optimizer", "exact_solver"):
        if key in route:
            template[key] = copy.deepcopy(route[key])

    candidates = _candidate_templates(template, avoid_blocks, segment_infos, normalized_blocks, origin, route)
    if len(candidates) == 1 and not avoid_blocks:
        return {"version": 1, "kind": "exact_template", "exact_template": candidates[0]["exact_template"]}
    return {
        "version": 1,
        "kind": "block_route_candidate_bundle",
        "name": route.get("name", "block_route"),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _route_landing_blocks(route: dict[str, Any]) -> list[dict[str, Any]]:
    if "landing_blocks" in route and "blocks" in route:
        raise ValueError("use either landing_blocks or legacy blocks, not both")
    blocks = route.get("landing_blocks", route.get("blocks"))
    if not isinstance(blocks, list) or len(blocks) < 2:
        raise ValueError("block route requires at least two landing_blocks")
    return blocks


def _normalize_block(block: dict[str, Any], index: int, default_run_ticks: int) -> dict[str, Any]:
    if not isinstance(block, dict):
        raise ValueError("each block must be an object")
    run_ticks = int(block.get("run_ticks", default_run_ticks))
    if run_ticks < 0:
        raise ValueError(f"block {index} run_ticks must be >= 0")
    width = float(block.get("width", 1.0))
    length = float(block.get("length", 1.0))
    if width <= 0 or length <= 0:
        raise ValueError(f"block {index} width/length must be > 0")
    block_id = str(block.get("id", f"b{index}"))
    return {
        "kind": "landing",
        "id": _safe_id(block_id),
        "x": float(block["x"]),
        "y": float(block["y"]),
        "z": float(block["z"]),
        "width": width,
        "length": length,
        "run_ticks": run_ticks,
    }


def _normalize_avoid_block(block: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(block, dict):
        raise ValueError("each avoid block must be an object")
    width = float(block.get("width", 1.0))
    length = float(block.get("length", 1.0))
    height = float(block.get("height", 1.0))
    if width <= 0 or length <= 0 or height <= 0:
        raise ValueError(f"avoid block {index} width/length/height must be > 0")
    between = block.get("between")
    if not (isinstance(between, list) and len(between) == 2 and all(isinstance(item, str) for item in between)):
        raise ValueError(f"avoid block {index} requires between: [from_landing_id, to_landing_id]")
    block_id = str(block.get("id", f"avoid{index}"))
    return {
        "kind": "avoid",
        "id": _safe_id(block_id),
        "x": float(block["x"]),
        "y": float(block["y"]),
        "z": float(block["z"]),
        "width": width,
        "length": length,
        "height": height,
        "between": [_safe_id(between[0]), _safe_id(between[1])],
        "corner_hints": [_safe_id(str(item)) for item in block.get("corner_hints", [])],
        "transition_tick_window": copy.deepcopy(block.get("transition_tick_window")),
    }


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    return cleaned or "block"


def _surface_y(block: dict[str, Any]) -> float:
    return float(block["y"]) + 1.0


def _ground_sprint_slot(slot: int, *, jump: bool) -> dict[str, Any]:
    return {
        "slot": slot,
        "kind": "movement",
        "controls": {"forward": 1, "strafe": 0, "jump": jump, "sneak": False, "sprint": True},
        "acceleration": {"medium": "ground", "input": "no45_forward"},
        "retention": {"medium": "flat_ground"},
    }


def _sprint_45_air_slot(slot: int) -> dict[str, Any]:
    return {
        "slot": slot,
        "kind": "movement",
        "controls": {"forward": 1, "strafe": 1, "jump": False, "sneak": False, "sprint": True},
        "acceleration": {"medium": "air", "input": "forward_45"},
        "retention": {"medium": "air"},
    }


def _position_bounds_constraint(
    constraint_id: str,
    slot: int,
    block: dict[str, Any],
    origin: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    min_x, max_x, min_z, max_z = _overlap_bounds(block, origin)
    return {
        "id": constraint_id,
        "type": "position_bounds",
        "slot": slot,
        "min_x": min_x,
        "max_x": max_x,
        "min_z": min_z,
        "max_z": max_z,
        "mathematica_tolerance": 0.0,
        "exact_tolerance": 0.0,
        "reason": reason,
    }


def _overlap_bounds(block: dict[str, Any], origin: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        _clean_float(float(block["x"]) - PLAYER_HALF_WIDTH - float(origin["x"])),
        _clean_float(float(block["x"]) + float(block["width"]) + PLAYER_HALF_WIDTH - float(origin["x"])),
        _clean_float(float(block["z"]) - PLAYER_HALF_WIDTH - float(origin["z"])),
        _clean_float(float(block["z"]) + float(block["length"]) + PLAYER_HALF_WIDTH - float(origin["z"])),
    )


def _candidate_templates(
    base_template: dict[str, Any],
    avoid_blocks: list[dict[str, Any]],
    segment_infos: list[dict[str, Any]],
    landing_blocks: list[dict[str, Any]],
    origin: dict[str, Any],
    route: dict[str, Any],
) -> list[dict[str, Any]]:
    if not avoid_blocks:
        return [{"id": "base", "avoid_choices": [], "exact_template": base_template}]

    segment_by_pair = {(segment["from"], segment["to"]): segment for segment in segment_infos}
    landing_by_id = {block["id"]: block for block in landing_blocks}
    landing_ids = {block["id"] for block in landing_blocks}
    per_avoid_options: list[list[dict[str, Any]]] = []
    for avoid in avoid_blocks:
        from_id, to_id = avoid["between"]
        if from_id not in landing_ids or to_id not in landing_ids:
            raise ValueError(f"avoid block {avoid['id']} references unknown landing block in between")
        segment = segment_by_pair.get((from_id, to_id))
        if segment is None:
            raise ValueError(f"avoid block {avoid['id']} must be between consecutive landing blocks")
        active_slots = _active_collision_slots(avoid, segment)
        endpoint_sides = _route_endpoint_sides(avoid, landing_by_id[from_id], landing_by_id[to_id], origin)
        schedules = _avoid_schedules(avoid, active_slots, endpoint_sides=endpoint_sides)
        per_avoid_options.append([
            {
                "avoid_id": avoid["id"],
                "between": avoid["between"],
                "active_slots": active_slots,
                "schedule": schedule,
                "constraints": _avoid_constraints(avoid, schedule, origin),
            }
            for schedule in schedules
        ])

    candidate_selection = route.get("candidate_selection", {})
    if not isinstance(candidate_selection, dict):
        raise ValueError("candidate_selection must be an object")
    max_candidates = int(candidate_selection.get("max_generated_candidates", 512))
    if max_candidates <= 0:
        raise ValueError("candidate_selection.max_generated_candidates must be > 0")

    candidates: list[dict[str, Any]] = []
    for index, combination in enumerate(itertools.product(*per_avoid_options)):
        if index >= max_candidates:
            break
        template = copy.deepcopy(base_template)
        candidate_id = f"candidate_{index + 1:03d}"
        avoid_choices = [_choice_metadata(choice) for choice in combination]
        template["name"] = f"{base_template.get('name', 'block_route')}_{candidate_id}"
        template["constraints"].extend(
            constraint
            for choice in combination
            for constraint in choice["constraints"]
        )
        template.setdefault("annotations", []).append({
            "kind": "block_route_candidate",
            "candidate_id": candidate_id,
            "avoid_choices": copy.deepcopy(avoid_choices),
        })
        candidates.append({
            "id": candidate_id,
            "avoid_choices": avoid_choices,
            "exact_template": template,
        })

    return candidates


def _active_collision_slots(avoid: dict[str, Any], segment: dict[str, Any]) -> list[int]:
    block_min_y = float(avoid["y"])
    block_max_y = block_min_y + float(avoid["height"])
    window = avoid.get("transition_tick_window")
    min_slot = max_slot = None
    if isinstance(window, list) and len(window) == 2:
        min_slot = int(window[0])
        max_slot = int(window[1])

    slots: list[int] = []
    for row in segment["vertical_trace"]:
        global_slot = int(segment["jump_slot"]) + int(row["slot"]) - 1
        if min_slot is not None and global_slot < min_slot:
            continue
        if max_slot is not None and global_slot > max_slot:
            continue
        feet_y = float(segment["from_surface_y"]) + float(row["y"])
        player_min_y = feet_y
        player_max_y = feet_y + PLAYER_HEIGHT
        if _intervals_overlap(player_min_y, player_max_y, block_min_y, block_max_y):
            slots.append(global_slot)
    return slots


def _intervals_overlap(a_min: float, a_max: float, b_min: float, b_max: float) -> bool:
    return a_min < b_max and b_min < a_max


def _avoid_schedules(
    avoid: dict[str, Any],
    active_slots: list[int],
    *,
    endpoint_sides: tuple[str | None, str | None] = (None, None),
) -> list[dict[str, Any]]:
    if not active_slots:
        return [{"kind": "inactive", "phases": []}]

    schedules: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    hints = set(avoid.get("corner_hints", []))
    allowed_hint_sides = _allowed_hint_sides(hints, endpoint_sides)

    def include_sides(sides: tuple[str, ...]) -> bool:
        if not allowed_hint_sides:
            return True
        return set(sides).issubset(allowed_hint_sides)

    def add_schedule(schedule: dict[str, Any]) -> None:
        key = tuple((phase["side"], tuple(phase["slots"])) for phase in schedule["phases"])
        if key not in seen:
            seen.add(key)
            schedules.append(schedule)

    start_side, end_side = endpoint_sides
    if start_side and end_side:
        if start_side == end_side:
            add_schedule({"kind": "route_side", "phases": [{"slots": active_slots, "side": start_side}]})
        elif len(active_slots) >= 2:
            for split_index in range(1, len(active_slots)):
                add_schedule({
                    "kind": "route_transition",
                    "transition_after_slot": active_slots[split_index - 1],
                    "phases": [
                        {"slots": active_slots[:split_index], "side": start_side},
                        {"slots": active_slots[split_index:], "side": end_side},
                    ],
                })

    for side in SIDE_ORDER:
        if include_sides((side,)):
            add_schedule({"kind": "single_side", "phases": [{"slots": active_slots, "side": side}]})

    if len(active_slots) >= 2:
        for side_a, side_b in TRANSITION_SIDE_PAIRS:
            if not include_sides((side_a, side_b)):
                continue
            for split_index in range(1, len(active_slots)):
                add_schedule({
                    "kind": "one_transition",
                    "transition_after_slot": active_slots[split_index - 1],
                    "phases": [
                        {"slots": active_slots[:split_index], "side": side_a},
                        {"slots": active_slots[split_index:], "side": side_b},
                    ],
                })

    if len(active_slots) >= 3:
        for side_a, side_b, side_c in TWO_CORNER_SIDE_TRIPLES:
            if not include_sides((side_a, side_b, side_c)):
                continue
            for first_split in range(1, len(active_slots) - 1):
                for second_split in range(first_split + 1, len(active_slots)):
                    add_schedule({
                        "kind": "two_corner",
                        "transition_after_slots": [
                            active_slots[first_split - 1],
                            active_slots[second_split - 1],
                        ],
                        "phases": [
                            {"slots": active_slots[:first_split], "side": side_a},
                            {"slots": active_slots[first_split:second_split], "side": side_b},
                            {"slots": active_slots[second_split:], "side": side_c},
                        ],
                    })

    return schedules


def _route_endpoint_sides(
    avoid: dict[str, Any],
    departure: dict[str, Any],
    target: dict[str, Any],
    origin: dict[str, Any],
) -> tuple[str | None, str | None]:
    min_x, max_x, min_z, max_z = _overlap_bounds(avoid, origin)
    return (
        _point_side(_block_center_x(departure, origin), _block_center_z(departure, origin), min_x, max_x, min_z, max_z),
        _point_side(_block_center_x(target, origin), _block_center_z(target, origin), min_x, max_x, min_z, max_z),
    )


def _block_center_x(block: dict[str, Any], origin: dict[str, Any]) -> float:
    return float(block["x"]) + float(block["width"]) / 2.0 - float(origin["x"])


def _block_center_z(block: dict[str, Any], origin: dict[str, Any]) -> float:
    return float(block["z"]) + float(block["length"]) / 2.0 - float(origin["z"])


def _point_side(x: float, z: float, min_x: float, max_x: float, min_z: float, max_z: float) -> str | None:
    candidates: list[tuple[float, str]] = []
    if x <= min_x:
        candidates.append((min_x - x, "west"))
    if x >= max_x:
        candidates.append((x - max_x, "east"))
    if z <= min_z:
        candidates.append((min_z - z, "north"))
    if z >= max_z:
        candidates.append((z - max_z, "south"))
    if not candidates:
        return None
    return max(candidates)[1]


def _allowed_hint_sides(hints: set[str], endpoint_sides: tuple[str | None, str | None]) -> set[str]:
    allowed = {side for side in endpoint_sides if side is not None}
    corner_names = {
        "north_west": {"north", "west"},
        "north_east": {"north", "east"},
        "south_west": {"south", "west"},
        "south_east": {"south", "east"},
    }
    for hint in hints:
        if hint in SIDE_ORDER:
            allowed.add(hint)
        elif hint in corner_names:
            allowed.update(corner_names[hint])
    return allowed


def _avoid_constraints(avoid: dict[str, Any], schedule: dict[str, Any], origin: dict[str, Any]) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    for phase_index, phase in enumerate(schedule["phases"]):
        side = phase["side"]
        for slot in phase["slots"]:
            constraints.append(_avoid_side_constraint(
                f"avoid_{avoid['id']}_{schedule['kind']}_p{phase_index + 1}_{side}_tick_{slot}",
                int(slot),
                avoid,
                origin,
                side,
            ))
    return constraints


def _avoid_side_constraint(
    constraint_id: str,
    slot: int,
    avoid: dict[str, Any],
    origin: dict[str, Any],
    side: str,
) -> dict[str, Any]:
    min_x, max_x, min_z, max_z = _overlap_bounds(avoid, origin)
    constraint: dict[str, Any] = {
        "id": constraint_id,
        "type": "position_bounds",
        "slot": slot,
        "mathematica_tolerance": 0.0,
        "exact_tolerance": 0.0,
        "reason": f"avoid {avoid['id']} on {side} side",
    }
    if side == "west":
        constraint["max_x"] = min_x
    elif side == "east":
        constraint["min_x"] = max_x
    elif side == "north":
        constraint["max_z"] = min_z
    elif side == "south":
        constraint["min_z"] = max_z
    else:
        raise ValueError(f"unknown avoid side: {side}")
    return constraint


def _choice_metadata(choice: dict[str, Any]) -> dict[str, Any]:
    return {
        "avoid_id": choice["avoid_id"],
        "between": copy.deepcopy(choice["between"]),
        "active_slots": copy.deepcopy(choice["active_slots"]),
        "schedule": copy.deepcopy(choice["schedule"]),
        "constraint_count": len(choice["constraints"]),
    }


def _clean_float(value: float) -> float:
    return round(value, 12)
