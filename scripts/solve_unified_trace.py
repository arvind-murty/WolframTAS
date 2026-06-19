#!/usr/bin/env python3
"""Run staged WolframTAS solving and emit one unified Markdown trace.

Input is the exact-template shape used by ``solve-exact-input``:
initial_state, movement_plan, constraints, exact_objective, and optional solver
settings. Output contains strict/relaxed Mathematica traces, the final exact
trace, and final macro rows/CSV.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from wolframtas_orchestrator.cli import read_json, run_staged_exact_flow


MACRO_COLUMNS = ["W", "A", "S", "D", "P", "N", "J", "YAW", "PITCH", "L", "R", "COUNT", "H"]


def _slot_facing_yaw_degrees(slots_by_number: dict[int, dict[str, Any]], slot: int, movement_radians: float) -> float:
    mv = math.remainder(float(movement_radians), 2.0 * math.pi)
    slot_obj = slots_by_number.get(slot, {})
    if slot_obj.get("kind") == "init":
        return -math.degrees(mv)
    controls = slot_obj.get("controls", {})
    forward = int(controls.get("forward", 0))
    strafe = int(controls.get("strafe", 0))
    offset = math.degrees(math.atan2(strafe, forward)) if (forward or strafe) else 0.0
    return -math.degrees(mv) + offset


def _mathematica_trace(solution: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    slots_by_number = {
        int(slot["slot"]): slot
        for slot in template.get("movement_plan", {}).get("slots", [])
    }
    directions = {
        int(direction["slot"]): direction
        for direction in solution.get("movement_directions", [])
    }
    points = sorted(solution.get("points", []), key=lambda point: int(point["slot"]))
    rows: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for point in points:
        slot = int(point["slot"])
        x = float(point.get("x", 0.0))
        z = float(point.get("z", 0.0))
        if previous is None:
            vx = 0.0
            vz = 0.0
        else:
            vx = x - float(previous.get("x", 0.0))
            vz = z - float(previous.get("z", 0.0))
        direction = directions.get(slot)
        movement_degrees = None
        yaw_degrees = None
        if direction is not None:
            radians = float(direction["radians"])
            movement_degrees = float(direction.get("degrees", math.degrees(radians)))
            yaw_degrees = _slot_facing_yaw_degrees(slots_by_number, slot, radians)
        rows.append(
            {
                "slot": slot,
                "x": x,
                "z": z,
                "vx": vx,
                "vz": vz,
                "yaw_degrees": yaw_degrees,
                "movement_direction_degrees": movement_degrees,
            }
        )
        previous = point

    return {
        "status": solution.get("status"),
        "objective_value": solution.get("objective_value"),
        "diagnostics": solution.get("diagnostics", {}),
        "states": rows,
    }


def _exact_trace(solution: dict[str, Any]) -> dict[str, Any]:
    yaw_by_state_tick = {
        int(angle["tick"]) + 1: angle
        for angle in solution.get("angles_discrete", [])
    }
    rows: list[dict[str, Any]] = []
    for state in solution.get("states_exact", []):
        tick = int(state["tick"])
        position = state.get("position", {})
        velocity = state.get("velocity", {})
        angle = yaw_by_state_tick.get(tick)
        rows.append(
            {
                "tick": tick,
                "x": float(position.get("x", 0.0)),
                "z": float(position.get("z", 0.0)),
                "vx": float(velocity.get("x", 0.0)),
                "vz": float(velocity.get("z", 0.0)),
                "yaw_degrees": None if angle is None else float(angle["yaw_degrees"]),
                "yaw_index": None if angle is None else int(angle["yaw_index"]),
            }
        )
    return {
        "status": solution.get("status"),
        "diagnostics": solution.get("diagnostics", {}),
        "states": rows,
    }


def _macro_csv_text(rows: list[dict[str, Any]]) -> str:
    lines = [",".join(MACRO_COLUMNS)]
    for row in rows:
        lines.append(
            f"{str(bool(row['w'])).lower()},"
            f"{str(bool(row['a'])).lower()},"
            f"{str(bool(row['s'])).lower()},"
            f"{str(bool(row['d'])).lower()},"
            f"{str(bool(row['p'])).lower()},"
            f"{str(bool(row['n'])).lower()},"
            f"{str(bool(row['j'])).lower()},"
            f"{row['yaw']},{row['pitch']},{row['l']},{row['r']},{row['count']},{row.get('h', 0)}"
        )
    return "\n".join(lines) + "\n"


def build_unified_trace(
    template: dict[str, Any],
    result: dict[str, Any],
    *,
    input_path: Path,
    default_relaxed_tolerance: float,
    solution_tolerance: float,
) -> dict[str, Any]:
    exact_solution = result["exact_solution"]
    macro_rows = exact_solution.get("macro_rows", [])
    return {
        "version": 1,
        "input": str(input_path),
        "name": template.get("name"),
        "tolerances": {
            "default_relaxed_tolerance": default_relaxed_tolerance,
            "solution_tolerance": solution_tolerance,
        },
        "strict": _mathematica_trace(result["strict_solution"], template),
        "relaxed": _mathematica_trace(result["relaxed_solution"], template),
        "exact": _exact_trace(exact_solution),
        "macro": {
            "columns": MACRO_COLUMNS,
            "rows": macro_rows,
            "csv": _macro_csv_text(macro_rows),
        },
    }


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(value) for value in row) + " |")
    return "\n".join(lines)


def _stage_summary(stage: dict[str, Any]) -> list[list[Any]]:
    diagnostics = stage.get("diagnostics", {})
    return [
        ["status", stage.get("status")],
        ["objective_value", stage.get("objective_value", "")],
        ["objective_deviation", diagnostics.get("objective_deviation", "")],
        ["final_residual_norm", diagnostics.get("final_residual_norm", "")],
        ["repair_iterations", diagnostics.get("repair_iterations", "")],
        ["candidate_evaluations", diagnostics.get("candidate_evaluations", "")],
    ]


def _mathematica_rows(stage: dict[str, Any]) -> list[list[Any]]:
    return [
        [
            row.get("slot"),
            row.get("x"),
            row.get("z"),
            row.get("vx"),
            row.get("vz"),
            row.get("yaw_degrees"),
            row.get("movement_direction_degrees"),
        ]
        for row in stage.get("states", [])
    ]


def _exact_rows(stage: dict[str, Any]) -> list[list[Any]]:
    return [
        [
            row.get("tick"),
            row.get("x"),
            row.get("z"),
            row.get("vx"),
            row.get("vz"),
            row.get("yaw_degrees"),
            row.get("yaw_index"),
        ]
        for row in stage.get("states", [])
    ]


def _macro_rows(rows: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        [
            row.get("w"),
            row.get("a"),
            row.get("s"),
            row.get("d"),
            row.get("p"),
            row.get("n"),
            row.get("j"),
            row.get("yaw"),
            row.get("pitch"),
            row.get("l"),
            row.get("r"),
            row.get("count"),
            row.get("h", 0),
        ]
        for row in rows
    ]


def render_markdown(trace: dict[str, Any]) -> str:
    lines = [
        f"# WolframTAS Unified Trace: {trace.get('name') or '(unnamed)'}",
        "",
        f"- Input: `{trace['input']}`",
        f"- Default relaxed tolerance: `{trace['tolerances']['default_relaxed_tolerance']}`",
        f"- Solution tolerance: `{trace['tolerances']['solution_tolerance']}`",
        "",
        "## Strict Mathematica",
        "",
        _markdown_table(["field", "value"], _stage_summary(trace["strict"])),
        "",
        _markdown_table(
            ["slot", "x", "z", "vx", "vz", "yaw_degrees", "movement_direction_degrees"],
            _mathematica_rows(trace["strict"]),
        ),
        "",
        "## Relaxed Mathematica",
        "",
        _markdown_table(["field", "value"], _stage_summary(trace["relaxed"])),
        "",
        _markdown_table(
            ["slot", "x", "z", "vx", "vz", "yaw_degrees", "movement_direction_degrees"],
            _mathematica_rows(trace["relaxed"]),
        ),
        "",
        "## Exact Solver",
        "",
        _markdown_table(["field", "value"], _stage_summary(trace["exact"])),
        "",
        _markdown_table(
            ["tick", "x", "z", "vx", "vz", "yaw_degrees", "yaw_index"],
            _exact_rows(trace["exact"]),
        ),
        "",
        "## Macro Rows",
        "",
        _markdown_table(MACRO_COLUMNS, _macro_rows(trace["macro"]["rows"])),
        "",
        "## Macro CSV",
        "",
        "```csv",
        trace["macro"]["csv"].rstrip(),
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run staged solving and emit a Markdown strict/relaxed/exact trace plus macro.")
    parser.add_argument("input", type=Path, help="Exact-template JSON input.")
    parser.add_argument("--out", type=Path, help="Write unified Markdown here. Defaults to stdout.")
    parser.add_argument("--wolframscript", default="wolframscript", help="wolframscript executable path.")
    parser.add_argument(
        "--optimizer-script",
        type=Path,
        default=Path("mathematica/optimize.wls"),
        help="Wolfram optimizer script to run with wolframscript -file.",
    )
    parser.add_argument("--default-relaxed-tolerance", type=float)
    parser.add_argument("--solution-tolerance", type=float)
    args = parser.parse_args(argv)

    template = read_json(args.input)
    solver_settings = template.get("solver", {})
    default_relaxed_tolerance = (
        args.default_relaxed_tolerance
        if args.default_relaxed_tolerance is not None
        else float(solver_settings.get("default_relaxed_tolerance", 0.0))
    )
    solution_tolerance = (
        args.solution_tolerance
        if args.solution_tolerance is not None
        else float(solver_settings.get("solution_tolerance", template.get("exact_objective", {}).get("solution_tolerance", 0.001)))
    )

    result = run_staged_exact_flow(
        template,
        wolframscript=args.wolframscript,
        optimizer_script=args.optimizer_script,
        default_relaxed_tolerance=default_relaxed_tolerance,
        solution_tolerance=solution_tolerance,
    )
    trace = build_unified_trace(
        template,
        result,
        input_path=args.input,
        default_relaxed_tolerance=default_relaxed_tolerance,
        solution_tolerance=solution_tolerance,
    )
    text = render_markdown(trace)
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
