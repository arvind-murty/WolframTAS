from __future__ import annotations

import math
import struct
from typing import Any


def fl(value: float) -> float:
    return struct.unpack("!f", struct.pack("!f", float(value)))[0]


def no45_forward_acceleration(movement: float) -> float:
    forward = fl(fl(1.0) * fl(0.98))
    distance = fl(forward * forward)
    distance = fl(math.sqrt(float(distance)))
    if distance < fl(1.0):
        distance = fl(1.0)
    distance = fl(movement / distance)
    return fl(forward * distance)


def flat_ground_retention() -> float:
    return fl(fl(0.91) * fl(0.6))


def air_retention() -> float:
    return fl(fl(0.91) * fl(1.0))


def slime_retention() -> float:
    return fl(fl(0.91) * fl(0.8))


def ice_retention() -> float:
    return fl(fl(0.91) * fl(0.98))


def water_retention() -> float:
    # mothball computes fl(0.8/0.91): the ratio in float64, then rounds to float32.
    water_slip = fl(0.8 / 0.91)
    return fl(fl(0.91) * water_slip)


def lava_retention() -> float:
    # mothball computes fl(0.5/0.91): the ratio in float64, then rounds to float32.
    lava_slip = fl(0.5 / 0.91)
    return fl(fl(0.91) * lava_slip)


def flat_sprint_jump_no45_mmu() -> float:
    movement = fl(0.1)
    movement = fl(float(movement) * (1.0 + float(fl(0.3))))
    drag = flat_ground_retention()
    movement = fl(movement * fl(fl(0.16277136) / fl(drag * drag * drag)))
    return float(no45_forward_acceleration(movement)) + float(fl(0.2))


def air_sprint_no45_mmu() -> float:
    movement = fl(0.02)
    movement = fl(float(movement) + float(movement) * 0.3)
    return no45_forward_acceleration(movement)


def air_walk_no45_mmu() -> float:
    return no45_forward_acceleration(fl(0.02))


def flat_walk_no45_mmu() -> float:
    return no45_forward_acceleration(fl(0.1))


def derive_movement_model(movement_plan: dict[str, Any]) -> dict[str, Any]:
    slots = movement_plan.get("slots")
    if not isinstance(slots, list) or not slots:
        raise ValueError("movement_plan.slots must be a non-empty list")

    imux: list[float] = []
    imuz: list[float] = []
    mmu: list[float] = []
    for slot in slots:
        if slot.get("kind", "movement") == "init":
            imux.append(float(slot["imux"]))
            imuz.append(float(slot["imuz"]))
            mmu.append(float(slot["speed"]))
            continue

        retention = derive_retention(slot)
        wall_axes = set(slot.get("wall_hit", {}).get("axes", []))
        imux.append(0.0 if "x" in wall_axes else retention)
        imuz.append(0.0 if "z" in wall_axes else retention)
        mmu.append(derive_mmu(slot))
    return {"arrays": {"imux": imux, "imuz": imuz, "mmu": mmu}}


def derive_simulation_arrays(movement_plan: dict[str, Any]) -> dict[str, list[float]]:
    return derive_movement_model(movement_plan)["arrays"]


def derive_movement_arrays(movement_plan: dict[str, Any]) -> dict[str, list[float]]:
    return derive_simulation_arrays(movement_plan)


def derive_retention(slot: dict[str, Any]) -> float:
    retention = slot.get("retention", {})
    medium = retention.get("medium")
    if medium == "flat_ground":
        return flat_ground_retention()
    if medium == "air":
        return air_retention()
    if medium == "slime":
        return slime_retention()
    if medium == "ice":
        return ice_retention()
    if medium == "water":
        return water_retention()
    if medium == "lava":
        return lava_retention()
    if medium == "none":
        return 0.0
    raise ValueError(f"unsupported retention medium: {medium!r}")


def derive_mmu(slot: dict[str, Any]) -> float:
    controls = slot.get("controls", {})
    acceleration = slot.get("acceleration", {})
    forward = controls.get("forward", 0)
    strafe = controls.get("strafe", 0)
    if forward == 0 and strafe == 0:
        return 0.0
    input_mode = acceleration.get("input", "no45_forward")
    if input_mode == "no45_forward" and (forward != 1 or strafe != 0):
        raise ValueError("no45_forward requires forward=1 and strafe=0")
    if input_mode == "forward_45" and (forward != 1 or abs(strafe) != 1):
        raise ValueError("forward_45 requires forward=1 and abs(strafe)=1")

    medium = acceleration.get("medium")
    sprint = bool(controls.get("sprint", False))
    jump = bool(controls.get("jump", False))
    if medium == "ground":
        if sprint and jump:
            movement = flat_sprint_jump_no45_mmu()
            if input_mode == "forward_45":
                movement += flat_ground_45_delta()
            return movement
        if not sprint:
            movement = flat_walk_no45_mmu()
            if input_mode == "forward_45":
                movement = 0.1
            return movement
    if medium == "air":
        if sprint:
            return air_sprint_45_mmu() if input_mode == "forward_45" else air_sprint_no45_mmu()
        return air_walk_45_mmu() if input_mode == "forward_45" else air_walk_no45_mmu()
    if medium in {"water", "lava"}:
        return fluid_45_mmu() if input_mode == "forward_45" else fluid_no45_mmu()
    raise ValueError(f"unsupported movement slot acceleration: medium={medium!r}, sprint={sprint}, jump={jump}")


def flat_ground_45_delta() -> float:
    movement = fl(0.1)
    movement = fl(float(movement) * (1.0 + float(fl(0.3))))
    drag = flat_ground_retention()
    movement = fl(movement * fl(fl(0.16277136) / fl(drag * drag * drag)))
    return float(movement) - float(no45_forward_acceleration(movement))


def air_sprint_45_mmu() -> float:
    movement = fl(0.02)
    return fl(float(movement) + float(movement) * 0.3)


def air_walk_45_mmu() -> float:
    return fl(0.02)


def fluid_no45_mmu() -> float:
    return no45_forward_acceleration(fl(0.02))


def fluid_45_mmu() -> float:
    return fl(0.02)
