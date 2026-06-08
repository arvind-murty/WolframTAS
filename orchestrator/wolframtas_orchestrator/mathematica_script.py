from __future__ import annotations

from decimal import Decimal
from typing import Any


def render_mathematica_script(problem: dict[str, Any], *, source_name: str | None = None) -> str:
    """Render the v1 Mathematica input schema as an inspectable Wolfram script."""
    validate_mathematica_problem(problem)

    lines: list[str] = []
    if source_name:
        lines.append(f"(* Generated from {source_name}. *)")
    else:
        lines.append("(* Generated from Mathematica input schema. *)")
    lines.append("(* Regenerate with: python3 -m wolframtas_orchestrator render-mathematica <input.json> --out <output.wls> *)")
    lines.append("(* Plotting, turn calculation, and output formatting are intentionally omitted. *)")
    lines.append("")
    lines.append(f"n = {problem['n']};")
    lines.append("F = Array[f, n];")
    lines.append("")

    for key, value in problem.get("constants", {}).items():
        lines.append(f"{key} = {wolfram_number(value)};")
    lines.append("")

    arrays = problem["arrays"]
    lines.append("Imux = " + wolfram_list(arrays["imux"]) + ";")
    lines.append("")
    lines.append("Imuz = " + wolfram_list(arrays["imuz"]) + ";")
    lines.append("")
    lines.append("Mmu = " + wolfram_list(arrays["mmu"]) + ";")
    lines.append("")

    lines.extend(
        [
            "coefFromIToT[imu_List, t_Integer] := Module[{c = ConstantArray[0., t]},",
            "  c[[t]] = 1.;",
            "  Do[c[[i]] = 1. + imu[[i]]*c[[i + 1]], {i, t - 1, 1, -1}];",
            "  c",
            "];",
            "",
            "cXAll = Table[coefFromIToT[Imux, t], {t, 1, n}];",
            "cZAll = Table[coefFromIToT[Imuz, t], {t, 1, n}];",
            "",
        ]
    )

    mmux_rules: list[str] = []
    mmuz_rules: list[str] = []
    for override in problem.get("component_overrides", []):
        rule = f"{override['slot']} -> {wolfram_number(override['value'])}"
        if override["target"] == "mmux":
            mmux_rules.append(rule)
        elif override["target"] == "mmuz":
            mmuz_rules.append(rule)
        else:
            raise ValueError(f"unsupported component override target: {override['target']}")

    lines.append("mmuxOverrideRules = {" + ", ".join(mmux_rules) + "};")
    lines.append("mmuzOverrideRules = {" + ", ".join(mmuz_rules) + "};")
    lines.append("")
    lines.append("Mmux[F_List] := ReplacePart[Take[Mmu, Length[F]]*Sin[F], mmuxOverrideRules];")
    lines.append("Mmuz[F_List] := ReplacePart[Take[Mmu, Length[F]]*Cos[F], mmuzOverrideRules];")
    lines.append("")
    lines.append("X[_, t_Integer /; t <= 0] := 0.;")
    lines.append("Z[_, t_Integer /; t <= 0] := 0.;")
    lines.append("")
    lines.append("X[F_List, t_Integer?Positive] := cXAll[[t]] . Mmux[F[[;; t]]];")
    lines.append("Z[F_List, t_Integer?Positive] := cZAll[[t]] . Mmuz[F[[;; t]]];")
    lines.append("")
    lines.append("obj = " + problem["objective"]["expression"] + ";")
    lines.append("")
    lines.append("cons = {")

    rendered_constraints = render_constraints(problem)
    for index, constraint in enumerate(rendered_constraints):
        suffix = "," if index < len(rendered_constraints) - 1 else ""
        lines.append(f"  (* {constraint['id']} *)")
        lines.append(f"  {constraint['expression']}{suffix}")
    lines.append("};")
    lines.append("")

    optimizer = problem.get("optimizer", {})
    accuracy_goal = wolfram_number(optimizer.get("accuracy_goal", 20))
    precision_goal = wolfram_number(optimizer.get("precision_goal", 20))
    objective_sense = problem["objective"].get("sense", "maximize")
    optimizer_symbol = "NMinimize" if objective_sense == "minimize" else "NMaximize"
    lines.append(f"sol = {optimizer_symbol}[{{obj, cons}}, F, AccuracyGoal -> {accuracy_goal},")
    lines.append(f"  PrecisionGoal -> {precision_goal}];")
    lines.append("fopt = F /. sol[[2]];")
    lines.append("")
    lines.append("points = Table[{X[fopt, t] - X[fopt, 0] + xoff,")
    lines.append("  Z[fopt, t] - Z[fopt, 0] + zoff}, {t, 0, n}];")
    lines.append("NumberForm[points, {Infinity, 5}]")

    return "\n".join(lines) + "\n"


def render_constraints(problem: dict[str, Any]) -> list[dict[str, str]]:
    constraints: list[dict[str, str]] = []
    for constraint in problem.get("constraints", []):
        constraints.extend(render_mathematica_constraint(constraint))

    for event in problem.get("inertia_events", []):
        constraints.extend(render_inertia_event(event))

    return constraints


def render_mathematica_constraint(constraint: dict[str, Any]) -> list[dict[str, str]]:
    if "expression" in constraint and constraint.get("type", "expression") == "expression":
        return [{"id": str(constraint["id"]), "expression": str(constraint["expression"])}]

    constraint_type = constraint.get("type")
    if constraint_type == "position_bounds":
        return render_position_bounds_constraint(constraint)
    if constraint_type == "position_delta_bound":
        return render_position_delta_bound_constraint(constraint)
    if constraint_type == "position_delta_offset_bound":
        return render_position_delta_offset_bound_constraint(constraint)
    if constraint_type == "facing_degrees_equal":
        return render_facing_degrees_equal_constraint(constraint)
    raise ValueError(f"unsupported Mathematica constraint shape: {constraint!r}")


def render_position_bounds_constraint(constraint: dict[str, Any]) -> list[dict[str, str]]:
    constraint_id = str(constraint["id"])
    slot = int(constraint["slot"])
    tolerance = wolfram_number(float(constraint.get("mathematica_tolerance", 0.0)))
    rendered: list[dict[str, str]] = []
    for key, function, sense in (
        ("min_x", "X", ">="),
        ("max_x", "X", "<="),
        ("min_z", "Z", ">="),
        ("max_z", "Z", "<="),
    ):
        if key not in constraint:
            continue
        raw_value = wolfram_number(constraint[key])
        value = f"({raw_value} + {tolerance})" if key.startswith("min_") else f"({raw_value} - {tolerance})"
        rendered.append(
            {
                "id": f"{constraint_id}_{key}",
                "expression": f"{function}[F, {slot}] {sense} {value}",
            }
        )
    if not rendered:
        raise ValueError(f"position_bounds constraint has no bounds: {constraint_id}")
    return rendered


def render_position_delta_bound_constraint(constraint: dict[str, Any]) -> list[dict[str, str]]:
    constraint_id = str(constraint["id"])
    axis = str(constraint["axis"])
    lhs_slot = int(constraint["lhs_slot"])
    rhs_slot = int(constraint["rhs_slot"])
    sense = str(constraint["sense"])
    value = float(constraint["value"])
    tolerance = float(constraint.get("mathematica_tolerance", 0.0))
    function = "X" if axis == "x" else "Z"
    if axis not in ("x", "z"):
        raise ValueError(f"position_delta_bound axis must be x or z: {constraint_id}")
    if sense not in (">=", "<="):
        raise ValueError(f"position_delta_bound sense must be >= or <=: {constraint_id}")
    threshold = value + tolerance if sense == ">=" else value - tolerance
    return [
        {
            "id": constraint_id,
            "expression": (
                f"{function}[F, {lhs_slot}] - {function}[F, {rhs_slot}] {sense} "
                f"{wolfram_number(threshold)}"
            ),
        }
    ]


def render_position_delta_offset_bound_constraint(constraint: dict[str, Any]) -> list[dict[str, str]]:
    constraint_id = str(constraint["id"])
    axis = str(constraint["axis"])
    lhs_slot = int(constraint["lhs_slot"])
    rhs_slot = int(constraint["rhs_slot"])
    sense = str(constraint["sense"])
    offset_symbol = str(constraint["offset_symbol"])
    offset_value = float(constraint.get("offset_value", 0.0))
    tolerance = float(constraint.get("mathematica_tolerance", 0.0))
    function = "X" if axis == "x" else "Z"
    if axis not in ("x", "z"):
        raise ValueError(f"position_delta_offset_bound axis must be x or z: {constraint_id}")
    if sense not in (">=", "<="):
        raise ValueError(f"position_delta_offset_bound sense must be >= or <=: {constraint_id}")
    shifted = offset_value + tolerance if sense == ">=" else offset_value - tolerance
    rhs = f"({offset_symbol} + {wolfram_number(shifted)})"
    return [
        {
            "id": constraint_id,
            "expression": f"{function}[F, {lhs_slot}] - {function}[F, {rhs_slot}] {sense} {rhs}",
        }
    ]


def render_facing_degrees_equal_constraint(constraint: dict[str, Any]) -> list[dict[str, str]]:
    constraint_id = str(constraint["id"])
    slot = int(constraint["slot"])
    degrees = float(constraint["degrees"])
    tolerance_degrees = float(constraint.get("mathematica_tolerance_degrees", 0.0))
    target = f"({wolfram_number(degrees)}*Pi/180)"
    tolerance = max(tolerance_degrees, 0.0)
    tolerance_radians = f"({wolfram_number(tolerance)}*Pi/180)"
    lower = f"({target} - {tolerance_radians})"
    upper = f"({target} + {tolerance_radians})"
    return [
        {
            "id": f"{constraint_id}_min",
            "expression": f"F[[{slot}]] >= {lower}",
        },
        {
            "id": f"{constraint_id}_max",
            "expression": f"F[[{slot}]] <= {upper}",
        },
    ]


def render_inertia_event(event: dict[str, Any]) -> list[dict[str, str]]:
    event_id = str(event["id"])
    axis = event["axis"]
    slot = event["slot"]
    retention = wolfram_number(event["retention_multiplier"])
    threshold = wolfram_number(event.get("threshold", 0.005))
    position = "X" if axis == "x" else "Z"
    positive_velocity = f"{retention}*({position}[F, {slot}] - {position}[F, {slot} - 1])"
    negative_velocity = f"{retention}*({position}[F, {slot} - 1] - {position}[F, {slot}])"

    if event["type"] == "hit":
        return [
            {"id": f"{event_id}_positive_bound", "expression": f"{positive_velocity} <= {threshold}"},
            {"id": f"{event_id}_negative_bound", "expression": f"{negative_velocity} <= {threshold}"},
        ]

    if event["type"] == "avoid":
        direction = event["direction"]
        velocity = positive_velocity if direction == "positive" else negative_velocity
        return [{"id": f"{event_id}_{direction}_avoid", "expression": f"{velocity} >= {threshold}"}]

    raise ValueError(f"unsupported inertia event type: {event['type']}")


def validate_mathematica_problem(problem: dict[str, Any]) -> None:
    if problem.get("version") != 1:
        raise ValueError("only Mathematica input schema version 1 is supported")
    if problem.get("slot_indexing") != "1_based":
        raise ValueError("only 1_based slot indexing is supported")
    n = problem.get("n")
    if not isinstance(n, int) or n < 1:
        raise ValueError("n must be a positive integer")
    arrays = problem.get("arrays")
    if not isinstance(arrays, dict):
        raise ValueError("arrays must be an object")
    for key in ("imux", "imuz", "mmu"):
        values = arrays.get(key)
        if not isinstance(values, list) or len(values) < n:
            raise ValueError(f"arrays.{key} must contain at least n values")
    objective = problem.get("objective")
    if not isinstance(objective, dict) or not objective.get("expression"):
        raise ValueError("objective.expression is required")


def wolfram_list(values: list[Any], *, per_line: int = 12) -> str:
    chunks: list[str] = []
    for index in range(0, len(values), per_line):
        chunk = ", ".join(wolfram_number(value) for value in values[index : index + per_line])
        chunks.append("  " + chunk)
    return "{\n" + ",\n".join(chunks) + "\n}"


def wolfram_number(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("booleans are not valid Wolfram numeric values")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(Decimal(repr(value)), "f")
    raise ValueError(f"expected numeric value, got {type(value).__name__}")
