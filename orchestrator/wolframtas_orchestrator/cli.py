from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the WolframTAS optimization pipeline.")
    parser.add_argument("request", type=Path, help="Optimization request JSON from the mod.")
    parser.add_argument("--mathematica-command", nargs="+", help="Command that emits approximate solution JSON.")
    parser.add_argument("--solver-command", nargs="+", help="Command that reads approximate JSON on stdin and emits exact JSON.")
    parser.add_argument("--approx-solution", type=Path, help="Use an existing approximate solution fixture.")
    parser.add_argument("--exact-solution-out", type=Path, required=True, help="Path for exact solution JSON.")

    args = parser.parse_args(argv)

    request = read_json(args.request)
    validate_request_shape(request)

    if args.approx_solution is not None:
        approximate_solution = read_json(args.approx_solution)
    elif args.mathematica_command:
        approximate_solution = run_json_producer(args.mathematica_command, request)
    else:
        parser.error("provide either --approx-solution or --mathematica-command")

    if args.solver_command:
        exact_solution = run_json_filter(args.solver_command, approximate_solution)
    else:
        exact_solution = fixture_exact_solution(approximate_solution, request)

    args.exact_solution_out.parent.mkdir(parents=True, exist_ok=True)
    args.exact_solution_out.write_text(json.dumps(exact_solution, indent=2) + "\n", encoding="utf-8")
    return 0


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_request_shape(request: dict[str, Any]) -> None:
    required = {
        "version",
        "minecraft_version",
        "angle_domain",
        "start_state",
        "keyboard_inputs",
        "constraints",
        "objectives",
        "solver",
    }
    missing = sorted(required.difference(request))
    if missing:
        raise ValueError(f"optimization request missing fields: {', '.join(missing)}")
    if request["minecraft_version"] != "1.8.9":
        raise ValueError("WolframTAS currently targets Minecraft 1.8.9")


def run_json_producer(command: list[str], request: dict[str, Any]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=True,
    )
    return parse_process_json(command[0], completed.stdout)


def run_json_filter(command: list[str], payload: dict[str, Any]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return parse_process_json(command[0], completed.stdout)


def parse_process_json(name: str, stdout: str) -> dict[str, Any]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} did not emit valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} must emit a JSON object")
    return value


def fixture_exact_solution(approximate_solution: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    keyboard_by_tick = {row["tick"]: row for row in request.get("keyboard_inputs", [])}
    macro_rows = []
    angles_discrete = []

    for angle in approximate_solution.get("angles", []):
        tick = int(angle["tick"])
        yaw_degrees = snap_degrees(float(angle["yaw"]))
        pitch_degrees = snap_degrees(float(angle["pitch"]))
        keyboard = keyboard_by_tick.get(tick, empty_keyboard(tick))

        angles_discrete.append(
            {
                "tick": tick,
                "yaw_index": degrees_to_index(yaw_degrees),
                "pitch_index": degrees_to_index(pitch_degrees),
                "yaw_degrees": yaw_degrees,
                "pitch_degrees": pitch_degrees,
            }
        )
        macro_rows.append(
            {
                "tick": tick,
                "yaw": yaw_degrees,
                "pitch": pitch_degrees,
                "forward": keyboard["forward"],
                "strafe": keyboard["strafe"],
                "jump": keyboard["jump"],
                "sneak": keyboard["sneak"],
                "sprint": keyboard["sprint"],
            }
        )

    return {
        "version": 1,
        "status": "solved",
        "angles_discrete": angles_discrete,
        "states_exact": [],
        "macro_rows": macro_rows,
        "diagnostics": {"mode": "fixture"},
    }


def empty_keyboard(tick: int) -> dict[str, Any]:
    return {
        "tick": tick,
        "forward": 0,
        "strafe": 0,
        "jump": False,
        "sneak": False,
        "sprint": False,
    }


def degrees_to_index(degrees: float) -> int:
    return round((degrees % 360.0) / 360.0 * 16384.0) % 16384


def snap_degrees(degrees: float) -> float:
    return degrees_to_index(degrees) * 360.0 / 16384.0


if __name__ == "__main__":
    sys.exit(main())
