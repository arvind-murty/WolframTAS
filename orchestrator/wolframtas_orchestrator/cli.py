from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .mathematica_script import render_mathematica_constraint, render_mathematica_script
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
    if argv and argv[0] == "solve-command":
        return solve_command_command(argv[1:])

    parser = argparse.ArgumentParser(description="Run the WolframTAS optimization pipeline.")
    parser.add_argument("request", type=Path, help="Optimization request JSON from the mod.")
    parser.add_argument("--mathematica-command", nargs="+", help="Command that emits approximate solution JSON.")
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


def run_staged_exact_flow(
    exact_template: dict[str, Any],
    *,
    wolframscript: str,
    optimizer_script: Path,
    solver_command: list[str] | None = None,
    default_relaxed_tolerance: float,
    solution_tolerance: float,
    macro_csv_out: Path | None = None,
) -> dict[str, Any]:
    """Run the staged Mathematica (strict + relaxed) optimize then the Python
    exact solver for an exact-solver template. Returns the strict/relaxed
    Mathematica solutions, the generated exact-solver input, and the exact
    solution. If macro_csv_out is given, writes the macro CSV there."""
    strict_problem = exact_template_to_mathematica_problem(
        exact_template, constraint_tolerance=0.0, fill_missing_tolerance=False
    )
    skip_relaxed_wolfram = default_relaxed_tolerance == 0.0
    relaxed_problem = exact_template_to_mathematica_problem(
        exact_template, constraint_tolerance=default_relaxed_tolerance, fill_missing_tolerance=True
    )

    with tempfile.TemporaryDirectory(prefix="wolframtas-solve-") as directory:
        strict_input = Path(directory) / "strict.json"
        strict_input.write_text(json.dumps(materialize_mathematica_problem(strict_problem)), encoding="utf-8")
        strict_solution = run_wolfram_file(wolframscript, optimizer_script, strict_input)
        if skip_relaxed_wolfram:
            relaxed_solution = copy.deepcopy(strict_solution)
        else:
            relaxed_input = Path(directory) / "relaxed.json"
            relaxed_input.write_text(json.dumps(materialize_mathematica_problem(relaxed_problem)), encoding="utf-8")
            relaxed_solution = run_wolfram_file(wolframscript, optimizer_script, relaxed_input)

    assert_solution_close(strict_solution, relaxed_solution, solution_tolerance)
    strict_solution.setdefault("diagnostics", {})["stage"] = "strict"
    relaxed_solution.setdefault("diagnostics", {})["stage"] = "relaxed"
    relaxed_solution["diagnostics"]["strict_objective_value"] = float(strict_solution["objective_value"])
    relaxed_solution["diagnostics"]["objective_deviation"] = abs(
        float(relaxed_solution["objective_value"]) - float(strict_solution["objective_value"])
    )

    exact_input = build_exact_solver_input(exact_template, relaxed_solution, solution_tolerance)
    from .python_solver import solve as _py_solve, write_macro_csv as _write_csv
    exact_solution = _py_solve(exact_input)
    if macro_csv_out is not None:
        macro_csv_out.parent.mkdir(parents=True, exist_ok=True)
        _write_csv(macro_csv_out, exact_solution)

    return {
        "strict_solution": strict_solution,
        "relaxed_solution": relaxed_solution,
        "exact_input": exact_input,
        "exact_solution": exact_solution,
    }


def solve_exact_input_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run staged Mathematica and the exact solver for an exact-input template.")
    parser.add_argument("input", type=Path, help="Exact solver input template with movement_plan and constraints.")
    parser.add_argument("--strict-out", type=Path, required=True, help="Path for strict Mathematica solution JSON.")
    parser.add_argument("--relaxed-out", type=Path, required=True, help="Path for relaxed Mathematica solution JSON.")
    parser.add_argument("--exact-input-out", type=Path, required=True, help="Path for generated exact solver input JSON.")
    parser.add_argument("--exact-out", type=Path, required=True, help="Path for exact solver output JSON.")
    parser.add_argument("--solver-command", nargs="+", help="Ignored (kept for backward compat; Python solver is used).")
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

    result = run_staged_exact_flow(
        read_json(args.input),
        wolframscript=args.wolframscript,
        optimizer_script=args.optimizer_script,
        solver_command=args.solver_command,
        default_relaxed_tolerance=args.default_relaxed_tolerance,
        solution_tolerance=args.solution_tolerance,
    )

    for output_path, key in (
        (args.strict_out, "strict_solution"),
        (args.relaxed_out, "relaxed_solution"),
        (args.exact_input_out, "exact_input"),
        (args.exact_out, "exact_solution"),
    ):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = result[key]
        if key == "relaxed_solution" and args.default_relaxed_tolerance == 0.0:
            payload = result["strict_solution"]
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


def solve_command_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Optimize a mothball command end-to-end: parse -> Mathematica optimize -> exact solver -> macro CSV."
    )
    parser.add_argument("command", help="Mothball command string, e.g. 'sj45(12)'.")
    parser.add_argument("--name", help="Optional run name used in the exact template and auto output filenames.")
    parser.add_argument("--out-dir", type=Path, default=Path("out/solve-command"), help="Directory for auto-generated outputs.")
    parser.add_argument("--macro-out", type=Path, help="Path for the macro CSV.")
    parser.add_argument("--solver-command", nargs="+", help="Ignored (Python solver is used).")
    parser.add_argument(
        "--constraint-json",
        action="append",
        default=[],
        help="Inline JSON object constraint to append (repeatable).",
    )
    parser.add_argument(
        "--constraints-file",
        type=Path,
        help="JSON file containing constraints (array) or an object with a constraints array.",
    )
    parser.add_argument("--objective-axis", default="z", choices=["x", "z"], help="Axis to optimize (default z = travel distance).")
    parser.add_argument("--sense", default="maximize", choices=["maximize", "minimize"])
    parser.add_argument("--init-speed", type=float, default=0.0, help="Init-slot speed for chained start state.")
    parser.add_argument("--init-imux", type=float, default=0.91, help="Init-slot X retention multiplier.")
    parser.add_argument("--init-imuz", type=float, default=0.91, help="Init-slot Z retention multiplier.")
    parser.add_argument("--exact-out", type=Path, help="Optional path for the exact solution JSON.")
    parser.add_argument("--exact-input-out", type=Path, help="Optional path for the generated exact solver input JSON.")
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

    from .command_parser import command_to_exact_template

    macro_out, exact_input_out, exact_out = resolve_solve_command_outputs(
        args.name,
        args.out_dir,
        args.macro_out,
        args.exact_input_out,
        args.exact_out,
    )
    constraints = parse_cli_constraints(args.constraint_json, args.constraints_file)

    exact_template = command_to_exact_template(
        args.command,
        objective_axis=args.objective_axis,
        sense=args.sense,
        init_speed=args.init_speed,
        init_imux=args.init_imux,
        init_imuz=args.init_imuz,
    )
    if args.name:
        exact_template["name"] = args.name
    exact_template["constraints"] = constraints
    result = run_staged_exact_flow(
        exact_template,
        wolframscript=args.wolframscript,
        optimizer_script=args.optimizer_script,
        default_relaxed_tolerance=args.default_relaxed_tolerance,
        solution_tolerance=args.solution_tolerance,
        macro_csv_out=macro_out,
    )
    if exact_input_out is not None:
        exact_input_out.parent.mkdir(parents=True, exist_ok=True)
        exact_input_out.write_text(json.dumps(result["exact_input"], indent=2) + "\n", encoding="utf-8")
    if exact_out is not None:
        exact_out.parent.mkdir(parents=True, exist_ok=True)
        exact_out.write_text(json.dumps(result["exact_solution"], indent=2) + "\n", encoding="utf-8")
    return 0


def parse_cli_constraints(constraint_json: list[str], constraints_file: Path | None) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    for text in constraint_json:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid --constraint-json value: {text!r}") from exc
        if not isinstance(value, dict):
            raise ValueError("--constraint-json expects a JSON object")
        constraints.append(value)

    if constraints_file is None:
        return constraints

    with constraints_file.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("--constraints-file array entries must be JSON objects")
            constraints.append(item)
        return constraints
    if isinstance(payload, dict):
        maybe_constraints = payload.get("constraints")
        if not isinstance(maybe_constraints, list):
            raise ValueError("--constraints-file object must contain a constraints array")
        for item in maybe_constraints:
            if not isinstance(item, dict):
                raise ValueError("--constraints-file constraints entries must be JSON objects")
            constraints.append(item)
        return constraints
    raise ValueError("--constraints-file must contain a JSON array or object")


def resolve_solve_command_outputs(
    name: str | None,
    out_dir: Path,
    macro_out: Path | None,
    exact_input_out: Path | None,
    exact_out: Path | None,
) -> tuple[Path, Path | None, Path | None]:
    if name is not None:
        stem = output_stem(name)
        if macro_out is None:
            macro_out = out_dir / f"{stem}_macro.csv"
        if exact_input_out is None:
            exact_input_out = out_dir / f"{stem}_exact_input.json"
        if exact_out is None:
            exact_out = out_dir / f"{stem}_exact_solution.json"
    if macro_out is None:
        raise ValueError("solve-command requires --macro-out, or provide --name for auto output filenames")
    return macro_out, exact_input_out, exact_out


def output_stem(name: str) -> str:
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("--name must not be blank")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", trimmed)


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
        rendered_constraints.extend(render_mathematica_constraint(constraint))
    materialized["constraints"] = rendered_constraints
    return materialized


def exact_template_to_mathematica_problem(
    exact_template: dict[str, Any],
    *,
    constraint_tolerance: float,
    fill_missing_tolerance: bool,
) -> dict[str, Any]:
    movement_model = derive_movement_model(exact_template["movement_plan"])
    arrays = copy.deepcopy(movement_model["arrays"])
    inertia_events = mathematica_inertia_events(exact_template.get("inertia_events", []), arrays)
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
        "arrays": arrays,
        "component_overrides": copy.deepcopy(exact_template.get("component_overrides", [])),
        "inertia_events": inertia_events,
        "objective": {
            "sense": objective.get("sense", "maximize"),
            "expression": objective.get("expression", f"{function}[F, {slot}]"),
        },
        "constraints": constraints,
        "optimizer": copy.deepcopy(exact_template.get("optimizer", {"accuracy_goal": 20, "precision_goal": 20})),
    }


def mathematica_inertia_events(events: list[dict[str, Any]], arrays: dict[str, list[float]]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for event in copy.deepcopy(events):
        axis = event["axis"]
        slot = int(event["slot"])
        array_key = "imux" if axis == "x" else "imuz"
        event["retention_multiplier"] = arrays[array_key][slot - 1]
        if event["type"] == "hit":
            arrays[array_key][slot - 1] = 0.0
        rendered.append(event)
    return rendered


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
    exact_supported_types = {
        "position_bounds",
        "position_delta_bound",
        "position_delta_offset_bound",
        "facing_degrees_equal",
    }
    supported_constraints: list[dict[str, Any]] = []
    skipped_constraints: list[dict[str, Any]] = []
    for constraint in exact_input.get("constraints", []):
        constraint_type = constraint.get("type")
        if constraint_type in exact_supported_types:
            supported_constraints.append(constraint)
        else:
            skipped_constraints.append(constraint)
    exact_input["constraints"] = supported_constraints
    if skipped_constraints:
        exact_input.setdefault("annotations", []).append(
            {
                "kind": "unsupported_exact_constraints",
                "reason": "constraints used for Mathematica but skipped by exact solver",
                "constraints": skipped_constraints,
            }
        )
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
        "slot_indexing",
        "n",
        "angle_domain",
        "initial_state",
        "movement_plan",
        "constraints",
        "exact_objective",
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
    keyboard_by_tick = movement_controls_by_tick(request)
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
        "diagnostics": {
            "mode": "fixture",
            "state_count": 0,
            "initial_residual_norm": "0",
            "final_residual_norm": "0",
            "worst_constraint_id": "",
            "candidate_evaluations": 0,
            "repair_iterations": 0,
            "exact_objective_value": "0",
            "objective_deviation": "0",
            "changed_angle_indices": [],
        },
    }


def movement_controls_by_tick(request: dict[str, Any]) -> dict[int, dict[str, Any]]:
    controls: dict[int, dict[str, Any]] = {}
    for slot in request.get("movement_plan", {}).get("slots", []):
        if slot.get("kind") != "movement":
            continue
        controls[int(slot["slot"]) - 1] = slot["controls"]
    return controls


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
