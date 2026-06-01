from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .mathematica_script import render_mathematica_script, render_position_bounds_constraint
from .movement_model import derive_movement_model


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "render-mathematica":
        return render_mathematica_command(argv[1:])
    if argv and argv[0] == "run-mathematica":
        return run_mathematica_command(argv[1:])
    if argv and argv[0] == "run-mathematica-staged":
        return run_mathematica_staged_command(argv[1:])
    if argv and argv[0] == "solve-exact-input":
        return solve_exact_input_command(argv[1:])

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


def render_mathematica_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Render a Mathematica input schema file as a Wolfram script.")
    parser.add_argument("input", type=Path, help="Mathematica input schema JSON.")
    parser.add_argument("--out", type=Path, required=True, help="Path for generated .wls script.")
    args = parser.parse_args(argv)

    problem = read_json(args.input)
    script = render_mathematica_script(problem, source_name=str(args.input))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(script, encoding="utf-8")
    return 0


def run_mathematica_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run Mathematica on a Mathematica input schema file.")
    parser.add_argument("input", type=Path, help="Mathematica input schema JSON.")
    parser.add_argument("--approx-out", type=Path, required=True, help="Path for approximate solution JSON.")
    parser.add_argument("--wolframscript", default="wolframscript", help="wolframscript executable path.")
    parser.add_argument(
        "--optimizer-script",
        type=Path,
        default=Path("mathematica/optimize.wls"),
        help="Wolfram optimizer script to run with wolframscript -file.",
    )
    args = parser.parse_args(argv)

    read_json(args.input)
    approximate_solution = run_wolfram_file(args.wolframscript, args.optimizer_script, args.input)
    args.approx_out.parent.mkdir(parents=True, exist_ok=True)
    args.approx_out.write_text(json.dumps(approximate_solution, indent=2) + "\n", encoding="utf-8")
    return 0


def run_mathematica_staged_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run strict and relaxed Mathematica solves.")
    parser.add_argument("input", type=Path, help="Mathematica input schema JSON.")
    parser.add_argument("--strict-out", type=Path, required=True, help="Path for strict solution JSON.")
    parser.add_argument("--relaxed-out", type=Path, required=True, help="Path for relaxed solution JSON.")
    parser.add_argument("--wolframscript", default="wolframscript", help="wolframscript executable path.")
    parser.add_argument(
        "--optimizer-script",
        type=Path,
        default=Path("mathematica/optimize.wls"),
        help="Wolfram optimizer script to run with wolframscript -file.",
    )
    parser.add_argument("--default-relaxed-tolerance", type=float, default=0.0001)
    parser.add_argument("--solution-tolerance", type=float, default=0.001)
    args = parser.parse_args(argv)

    problem = read_json(args.input)
    strict_problem = with_constraint_tolerance(problem, 0.0, fill_missing=False)
    relaxed_problem = with_constraint_tolerance(problem, args.default_relaxed_tolerance, fill_missing=True)

    with tempfile.TemporaryDirectory(prefix="wolframtas-staged-") as directory:
        strict_input = Path(directory) / "strict.json"
        relaxed_input = Path(directory) / "relaxed.json"
        strict_input.write_text(json.dumps(materialize_mathematica_problem(strict_problem)), encoding="utf-8")
        relaxed_input.write_text(json.dumps(materialize_mathematica_problem(relaxed_problem)), encoding="utf-8")
        strict_solution = run_wolfram_file(args.wolframscript, args.optimizer_script, strict_input)
        relaxed_solution = run_wolfram_file(args.wolframscript, args.optimizer_script, relaxed_input)

    strict_objective = float(strict_solution["objective_value"])
    relaxed_objective = float(relaxed_solution["objective_value"])
    objective_deviation = abs(relaxed_objective - strict_objective)
    if objective_deviation > args.solution_tolerance:
        raise RuntimeError(
            "relaxed Mathematica objective deviated by "
            f"{objective_deviation}, exceeding solution_tolerance {args.solution_tolerance}"
        )

    strict_solution.setdefault("diagnostics", {})["stage"] = "strict"
    relaxed_solution.setdefault("diagnostics", {})["stage"] = "relaxed"
    relaxed_solution["diagnostics"]["strict_objective_value"] = strict_objective
    relaxed_solution["diagnostics"]["objective_deviation"] = objective_deviation

    args.strict_out.parent.mkdir(parents=True, exist_ok=True)
    args.relaxed_out.parent.mkdir(parents=True, exist_ok=True)
    args.strict_out.write_text(json.dumps(strict_solution, indent=2) + "\n", encoding="utf-8")
    args.relaxed_out.write_text(json.dumps(relaxed_solution, indent=2) + "\n", encoding="utf-8")
    return 0


def solve_exact_input_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run staged Mathematica and the exact solver for an exact-input template.")
    parser.add_argument("input", type=Path, help="Exact solver input template with movement_plan and constraints.")
    parser.add_argument("--strict-out", type=Path, required=True, help="Path for strict Mathematica solution JSON.")
    parser.add_argument("--relaxed-out", type=Path, required=True, help="Path for relaxed Mathematica solution JSON.")
    parser.add_argument("--exact-input-out", type=Path, required=True, help="Path for generated exact solver input JSON.")
    parser.add_argument("--exact-out", type=Path, required=True, help="Path for exact solver output JSON.")
    parser.add_argument("--solver-command", nargs="+", required=True, help="Exact solver command that reads JSON on stdin.")
    parser.add_argument("--wolframscript", default="wolframscript", help="wolframscript executable path.")
    parser.add_argument(
        "--optimizer-script",
        type=Path,
        default=Path("mathematica/optimize.wls"),
        help="Wolfram optimizer script to run with wolframscript -file.",
    )
    parser.add_argument("--default-relaxed-tolerance", type=float, default=0.0001)
    parser.add_argument("--solution-tolerance", type=float, default=0.001)
    args = parser.parse_args(argv)

    exact_template = read_json(args.input)
    strict_problem = exact_template_to_mathematica_problem(
        exact_template,
        constraint_tolerance=0.0,
        fill_missing_tolerance=False,
    )
    relaxed_problem = exact_template_to_mathematica_problem(
        exact_template,
        constraint_tolerance=args.default_relaxed_tolerance,
        fill_missing_tolerance=True,
    )

    with tempfile.TemporaryDirectory(prefix="wolframtas-solve-") as directory:
        strict_input = Path(directory) / "strict.json"
        relaxed_input = Path(directory) / "relaxed.json"
        strict_input.write_text(json.dumps(materialize_mathematica_problem(strict_problem)), encoding="utf-8")
        relaxed_input.write_text(json.dumps(materialize_mathematica_problem(relaxed_problem)), encoding="utf-8")
        strict_solution = run_wolfram_file(args.wolframscript, args.optimizer_script, strict_input)
        relaxed_solution = run_wolfram_file(args.wolframscript, args.optimizer_script, relaxed_input)

    assert_solution_close(strict_solution, relaxed_solution, args.solution_tolerance)
    strict_solution.setdefault("diagnostics", {})["stage"] = "strict"
    relaxed_solution.setdefault("diagnostics", {})["stage"] = "relaxed"
    relaxed_solution["diagnostics"]["strict_objective_value"] = float(strict_solution["objective_value"])
    relaxed_solution["diagnostics"]["objective_deviation"] = abs(
        float(relaxed_solution["objective_value"]) - float(strict_solution["objective_value"])
    )

    exact_input = build_exact_solver_input(exact_template, relaxed_solution, args.solution_tolerance)
    exact_solution = run_json_filter(args.solver_command, exact_input)

    for output_path, payload in (
        (args.strict_out, strict_solution),
        (args.relaxed_out, relaxed_solution),
        (args.exact_input_out, exact_input),
        (args.exact_out, exact_solution),
    ):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


def with_constraint_tolerance(problem: dict[str, Any], tolerance: float, *, fill_missing: bool) -> dict[str, Any]:
    updated = copy.deepcopy(problem)
    for constraint in updated.get("constraints", []):
        if "mathematica_tolerance" in constraint or fill_missing:
            constraint["mathematica_tolerance"] = tolerance if not fill_missing else constraint.get("mathematica_tolerance", tolerance)
        if not fill_missing:
            constraint["mathematica_tolerance"] = 0.0
    return updated


def materialize_mathematica_problem(problem: dict[str, Any]) -> dict[str, Any]:
    materialized = copy.deepcopy(problem)
    rendered_constraints: list[dict[str, str]] = []
    for constraint in materialized.get("constraints", []):
        if "expression" in constraint:
            rendered_constraints.append({"id": str(constraint["id"]), "expression": str(constraint["expression"])})
        elif constraint.get("type") == "position_bounds":
            rendered_constraints.extend(render_position_bounds_constraint(constraint))
        else:
            raise ValueError(f"unsupported Mathematica constraint shape: {constraint!r}")
    materialized["constraints"] = rendered_constraints
    return materialized


def exact_template_to_mathematica_problem(
    exact_template: dict[str, Any],
    *,
    constraint_tolerance: float,
    fill_missing_tolerance: bool,
) -> dict[str, Any]:
    movement_model = derive_movement_model(exact_template["movement_plan"])
    constraints = copy.deepcopy(exact_template.get("constraints", []))
    for constraint in constraints:
        if fill_missing_tolerance:
            constraint["mathematica_tolerance"] = constraint.get("mathematica_tolerance", constraint_tolerance)
        else:
            constraint["mathematica_tolerance"] = 0.0

    objective = exact_template.get("exact_objective", {})
    axis = objective.get("axis", "z")
    slot = int(objective.get("slot", exact_template["n"]))
    function = "X" if axis == "x" else "Z"

    return {
        "version": 1,
        "name": exact_template.get("name", ""),
        "slot_indexing": "1_based",
        "n": exact_template["n"],
        "arrays": movement_model["arrays"],
        "component_overrides": copy.deepcopy(exact_template.get("component_overrides", [])),
        "objective": {
            "sense": objective.get("sense", "maximize"),
            "expression": objective.get("expression", f"{function}[F, {slot}]"),
        },
        "constraints": constraints,
        "optimizer": copy.deepcopy(exact_template.get("optimizer", {"accuracy_goal": 20, "precision_goal": 20})),
    }


def assert_solution_close(strict_solution: dict[str, Any], relaxed_solution: dict[str, Any], tolerance: float) -> None:
    strict_objective = float(strict_solution["objective_value"])
    relaxed_objective = float(relaxed_solution["objective_value"])
    objective_deviation = abs(relaxed_objective - strict_objective)
    if objective_deviation > tolerance:
        raise RuntimeError(
            "relaxed Mathematica objective deviated by "
            f"{objective_deviation}, exceeding solution_tolerance {tolerance}"
        )


def build_exact_solver_input(
    exact_template: dict[str, Any],
    relaxed_solution: dict[str, Any],
    solution_tolerance: float,
) -> dict[str, Any]:
    exact_input = copy.deepcopy(exact_template)
    exact_input["optimal_solution"] = {
        "status": relaxed_solution.get("status", "optimal"),
        "objective_value": relaxed_solution["objective_value"],
        "movement_directions": relaxed_solution["movement_directions"],
        "points": relaxed_solution.get("points", []),
        "diagnostics": relaxed_solution.get("diagnostics", {}),
    }
    if "exact_objective" in exact_input:
        exact_input["exact_objective"].setdefault("target_value", relaxed_solution["objective_value"])
        exact_input["exact_objective"].setdefault("solution_tolerance", solution_tolerance)
    return exact_input


def run_wolfram_file(wolframscript: str, optimizer_script: Path, input_path: Path) -> dict[str, Any]:
    command = [wolframscript, "-file", str(optimizer_script), str(input_path)]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"wolframscript failed: {detail}")
    return parse_process_json(wolframscript, completed.stdout)


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
                "w": keyboard["forward"] > 0,
                "a": keyboard["strafe"] > 0,
                "s": keyboard["forward"] < 0,
                "d": keyboard["strafe"] < 0,
                "p": keyboard["sprint"],
                "n": keyboard["sneak"],
                "j": keyboard["jump"],
                "yaw": yaw_degrees,
                "pitch": pitch_degrees,
                "l": 0,
                "r": 0,
                "count": 1,
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
    return round((degrees % 360.0) / 360.0 * 65536.0) % 65536


def snap_degrees(degrees: float) -> float:
    return degrees_to_index(degrees) * 360.0 / 65536.0


if __name__ == "__main__":
    sys.exit(main())
