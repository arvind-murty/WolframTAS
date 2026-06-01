#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def value_at(document, path):
    value = document
    for part in path.split("."):
        if "[" in part:
            name, index = part[:-1].split("[", 1)
            value = value[name][int(index)]
        else:
            value = value[part]
    return value


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def validate_exact_solution_schema(document):
    require(document.get("version") == 1, "version must be 1")
    require(document.get("status") in {"solved", "failed", "error"}, "invalid status")
    require(isinstance(document.get("angles_discrete"), list), "angles_discrete must be a list")
    require(isinstance(document.get("states_exact"), list), "states_exact must be a list")
    require(isinstance(document.get("macro_rows"), list), "macro_rows must be a list")
    diagnostics = document.get("diagnostics")
    require(isinstance(diagnostics, dict), "diagnostics must be an object")
    for key in (
        "mode",
        "state_count",
        "initial_residual_norm",
        "final_residual_norm",
        "worst_constraint_id",
        "candidate_evaluations",
        "repair_iterations",
        "exact_objective_value",
        "objective_deviation",
        "changed_angle_indices",
    ):
        require(key in diagnostics, f"diagnostics.{key} is required")

    for angle in document["angles_discrete"]:
        for key in ("tick", "yaw_index", "pitch_index", "yaw_degrees", "pitch_degrees"):
            require(key in angle, f"angle.{key} is required")
        require(0 <= angle["yaw_index"] <= 65535, "yaw_index out of range")
        require(0 <= angle["pitch_index"] <= 65535, "pitch_index out of range")

    for state in document["states_exact"]:
        for key in ("tick", "position", "velocity", "on_ground"):
            require(key in state, f"state.{key} is required")
        for vector_key in ("position", "velocity"):
            vector = state[vector_key]
            require(isinstance(vector, dict), f"state.{vector_key} must be an object")
            for axis in ("x", "y", "z"):
                require(isinstance(vector.get(axis), str), f"state.{vector_key}.{axis} must be a string")

    for row in document["macro_rows"]:
        for key in ("w", "a", "s", "d", "p", "n", "j"):
            require(isinstance(row.get(key), bool), f"macro row {key} must be boolean")
        for key in ("l", "r", "count"):
            require(isinstance(row.get(key), int), f"macro row {key} must be integer")
        require(row["count"] >= 1, "macro row count must be positive")

    for change in diagnostics["changed_angle_indices"]:
        for key in ("slot", "from", "to", "delta"):
            require(key in change, f"changed angle {key} is required")
        require(0 <= change["from"] <= 65535, "changed angle from out of range")
        require(0 <= change["to"] <= 65535, "changed angle to out of range")
        require(-32768 <= change["delta"] <= 32767, "changed angle delta out of range")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--expect", action="append", default=[])
    parser.add_argument("--expect-macro-line", action="append", default=[])
    parser.add_argument("--validate-exact-solution-schema", action="store_true")
    args = parser.parse_args()

    fixture = Path(args.input)
    command = [args.solver]
    macro_output_path = None
    temporary_directory = None
    if args.expect_macro_line:
        temporary_directory = tempfile.TemporaryDirectory(prefix="wolframtas-macro-")
        macro_output_path = Path(temporary_directory.name) / "macro.csv"
        command.extend(["--macro-csv-out", str(macro_output_path)])

    completed = subprocess.run(
        command,
        input=fixture.read_text(),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        return completed.returncode

    document = json.loads(completed.stdout)
    if args.validate_exact_solution_schema:
        try:
            validate_exact_solution_schema(document)
        except AssertionError as error:
            sys.stderr.write(f"{fixture}: exact solution schema validation failed: {error}\n")
            sys.stderr.write(completed.stdout)
            return 1
    for expectation in args.expect:
        path, expected = expectation.split("=", 1)
        actual = value_at(document, path)
        if str(actual) != expected:
            sys.stderr.write(
                f"{fixture}: expected {path}={expected!r}, got {actual!r}\n"
            )
            sys.stderr.write(completed.stdout)
            return 1
    if macro_output_path is not None:
        macro_lines = macro_output_path.read_text(encoding="utf-8").splitlines()
        for expected in args.expect_macro_line:
            if expected not in macro_lines:
                sys.stderr.write(f"{fixture}: expected macro CSV line {expected!r}\n")
                sys.stderr.write("\n".join(macro_lines) + "\n")
                return 1
    if temporary_directory is not None:
        temporary_directory.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
