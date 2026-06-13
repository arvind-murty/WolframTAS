"""Generate the shared movement-constants table — the SINGLE source of truth for
the imu (retention) and mmu (movement magnitude) constants used by the Python
solver and the Python orchestrator (Wolfram).

The values are computed in numpy float32, which is mothball's reference
semantics, with the same op order the solver uses. Emits:
  - orchestrator/wolframtas_orchestrator/movement_constants.json (for the orchestrator)

Run (needs numpy 1.26, NOT 2.x):
  .venv-oracle/bin/python tools/gen_movement_constants.py

Constants only. Operations that are not per-type constants (ladder +/-0.15 clamp,
web /4, sprint 1-tick air delay, the 0.005 inertia threshold, the forward/strafe
2D rotation) stay as logic in the solver.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

f32 = np.float32
REPO = Path(__file__).resolve().parents[1]

# Ground slipperiness per ground medium (Minecraft block slipperiness).
GROUND_SLIP = {"flat_ground": 0.6, "slime": 0.8, "ice": 0.98}


def retention(medium: str) -> float:
    # mothball drag = fl(0.91) * slip. Fluids compute slip = fl(num/0.91) (ratio
    # in float64 then rounded); ground/air/slime/ice multiply float32 slips.
    if medium == "air":
        return float(f32(f32(0.91) * f32(1.0)))
    if medium == "none":
        return 0.0
    if medium == "water":
        return float(f32(f32(0.91) * f32(0.8 / 0.91)))
    if medium == "lava":
        return float(f32(f32(0.91) * f32(0.5 / 0.91)))
    if medium in GROUND_SLIP:
        return float(f32(f32(0.91) * f32(GROUND_SLIP[medium])))
    raise ValueError(f"unknown retention medium: {medium}")


def ground_base_movement(ret_medium: str, sprint: bool) -> float:
    # movement = 0.1; if sprint: *1.3; movement *= 0.16277136 / drag^3.
    movement = f32(0.1)
    if sprint:
        movement = f32(float(movement) * (1.0 + float(f32(0.3))))
    drag = f32(retention(ret_medium))
    drag3 = f32(f32(drag * drag) * drag)
    movement = f32(movement * f32(f32(0.16277136) / drag3))
    return float(movement)


def air_base_movement(sprint: bool) -> float:
    movement = f32(0.02)
    if sprint:
        movement = f32(float(movement) + float(movement) * 0.3)
    return float(movement)


def input_factor(sneak: bool, strafe: int) -> float:
    # The velocity-contribution magnitude is base_movement * (D / max(D, 1)),
    # where D = |(forward, strafe)| after the sneak (0.3) and 0.98 input factors.
    # forward is always 1 for the supported inputs; strafe is 0 (no-45) or +/-1 (45).
    fwd = f32(float(f32(1.0)) * (0.3 if sneak else 1.0))
    fwd = f32(fwd * f32(0.98))
    strf = f32(float(f32(abs(strafe))) * (0.3 if sneak else 1.0))
    strf = f32(strf * f32(0.98))
    dist = f32(strf * strf + fwd * fwd)
    dist = f32(math.sqrt(float(dist)))
    denom = dist if dist >= f32(1.0) else f32(1.0)
    return float(f32(dist / denom))


def build() -> dict:
    retentions = {m: retention(m) for m in ["flat_ground", "air", "slime", "ice", "water", "lava", "none"]}
    base_movement = {}
    for med in GROUND_SLIP:
        base_movement[f"ground_{med}_walk"] = ground_base_movement(med, sprint=False)
        base_movement[f"ground_{med}_sprint"] = ground_base_movement(med, sprint=True)
    base_movement["air_walk"] = air_base_movement(False)
    base_movement["air_sprint"] = air_base_movement(True)
    base_movement["water"] = float(f32(0.02))
    base_movement["lava"] = float(f32(0.02))
    factors = {
        "no45": input_factor(sneak=False, strafe=0),
        "forward_45": input_factor(sneak=False, strafe=1),
        "no45_sneak": input_factor(sneak=True, strafe=0),
        "forward_45_sneak": input_factor(sneak=True, strafe=1),
    }
    return {
        "retention": retentions,
        "base_movement": base_movement,
        "input_factor": factors,
        "sprintjump_boost": float(f32(0.2)),
        # Cobweb cuts the move velocity to 1/4 on a web tick. Used by the Python
        # solver (real per-tick cut) and the orchestrator's Mathematica web
        # approximation. Exact in float32/float64, so no rounding concern.
        "web_motion_factor": 0.25,
    }


def main() -> None:
    table = build()
    json_path = REPO / "orchestrator/wolframtas_orchestrator/movement_constants.json"
    json_path.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {json_path}")
    print(json.dumps(table, indent=2))


if __name__ == "__main__":
    main()
