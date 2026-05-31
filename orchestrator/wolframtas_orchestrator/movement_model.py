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


def water_retention() -> float:
    water_slip = fl(fl(0.8) / fl(0.91))
    return fl(fl(0.91) * water_slip)


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
            velocity = slot["velocity"]
            mmu.append(math.hypot(float(velocity["x"]), float(velocity["z"])))
            continue

        retention = derive_retention(slot)
        imux.append(retention)
        imuz.append(retention)
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
    if medium == "water":
        return water_retention()
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
    if forward != 1 or strafe != 0:
        raise ValueError("only no-45 forward movement is supported by movement-plan v1")

    medium = acceleration.get("medium")
    sprint = bool(controls.get("sprint", False))
    jump = bool(controls.get("jump", False))
    if medium == "ground":
        if sprint and jump:
            return flat_sprint_jump_no45_mmu()
        if not sprint:
            return flat_walk_no45_mmu()
    if medium == "air":
        return air_sprint_no45_mmu() if sprint else air_walk_no45_mmu()
    raise ValueError(f"unsupported movement slot acceleration: medium={medium!r}, sprint={sprint}, jump={jump}")
