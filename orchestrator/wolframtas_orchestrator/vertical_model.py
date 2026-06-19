from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))


def jump_air_ticks(from_surface_y: float, to_surface_y: float, *, max_air_ticks: int = 80) -> int:
    """Return air movement slots after the one jump slot for a normal jump.

    Mothball's vertical helper reports a jump tier on the last airborne tick
    before the next vertical step would cross the landing surface. This function
    mirrors that tick order: one ground jump tick, then air ticks until the
    falling interval from current y to next y contains the target surface.
    """
    from cogs.movement.context import Context
    from cogs.movement.playerY import PlayerY

    target_delta = float(to_surface_y) - float(from_surface_y)
    player = PlayerY()
    ctx = Context(player, [{}], False, "y")

    ctx.args = {"jumping": True}
    player.move(ctx)

    for air_ticks in range(1, max_air_ticks + 1):
        ctx.args = {"airborne": True}
        player.move(ctx)
        if player.vy < 0 and _falling_step_contains(player.y, player.y + player.vy, target_delta):
            return air_ticks

    raise ValueError(
        f"target surface y={to_surface_y} is not reachable from y={from_surface_y} "
        f"within {max_air_ticks} air ticks"
    )


def vertical_trace(from_surface_y: float, to_surface_y: float, *, max_air_ticks: int = 80) -> list[dict[str, Any]]:
    from cogs.movement.context import Context
    from cogs.movement.playerY import PlayerY

    target_delta = float(to_surface_y) - float(from_surface_y)
    player = PlayerY()
    ctx = Context(player, [{}], False, "y")
    rows: list[dict[str, Any]] = []

    ctx.args = {"jumping": True}
    player.move(ctx)
    rows.append({"slot": 1, "phase": "jump", "y": player.y, "vy": player.vy, "contains_target": player.y == target_delta})

    for air_ticks in range(1, max_air_ticks + 1):
        ctx.args = {"airborne": True}
        player.move(ctx)
        contains = player.vy < 0 and _falling_step_contains(player.y, player.y + player.vy, target_delta)
        rows.append({"slot": air_ticks + 1, "phase": "air", "y": player.y, "vy": player.vy, "contains_target": contains})
        if contains:
            break

    return rows


def _falling_step_contains(current_y: float, next_y: float, target_y: float) -> bool:
    return current_y >= target_y >= next_y
