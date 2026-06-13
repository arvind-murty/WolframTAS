# Mothball Command to Wolfram Script

This workflow turns a mothball command string plus optional typed constraints
into an inspectable Wolfram `.wls` script.

Use this when you want to inspect or hand-run the Mathematica model before the
full `solve-command` pipeline. The full pipeline command still exists, but it
does not currently keep the intermediate Mathematica input/script files.

## Prerequisites

Use the project oracle environment:

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python --version
```

The venv needs numpy 1.26 and `evalidate` because the mothball parser/oracle
imports the vendored mothball engine.

## Inputs

The command input is a mothball command string, for example:

```text
sj45(12)
sprint(8, 45)
walk[hitz=0.04](1) walk(2)
setvx(-0.269196777381033) sj(1, 3.7353515625)
```

The parser lives in
`orchestrator/wolframtas_orchestrator/command_parser.py` and supports the command
coverage validated by `e2e/check_command_sim.py`.

Constraints are exact-template typed constraint objects. The most useful ones
are:

```json
{
  "id": "land_z",
  "type": "position_bounds",
  "slot": 13,
  "min_z": 3.0,
  "exact_tolerance": 0.0,
  "mathematica_tolerance": 0.0001
}
```

```json
{
  "id": "delta_z",
  "type": "position_delta_bound",
  "axis": "z",
  "lhs_slot": 13,
  "rhs_slot": 1,
  "sense": ">=",
  "value": 3.0,
  "exact_tolerance": 0.0,
  "mathematica_tolerance": 0.0001
}
```

Supported typed constraints for rendering are:

- `position_bounds`
- `position_delta_bound`
- `position_delta_offset_bound`
- `facing_degrees_equal`
- `expression`

Raw `expression` constraints are rendered for Mathematica, but they are skipped
by the exact solver later because there is no typed exact-check equivalent.

## One-File Example

Create a small constraints file:

```sh
mkdir -p /tmp/wolframtas
cat > /tmp/wolframtas/constraints.json <<'JSON'
[
  {
    "id": "min_travel",
    "type": "position_delta_bound",
    "axis": "z",
    "lhs_slot": 13,
    "rhs_slot": 1,
    "sense": ">=",
    "value": 3.0,
    "mathematica_tolerance": 0.0001,
    "exact_tolerance": 0.0
  }
]
JSON
```

Render the strict Mathematica model from a mothball command:

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python - <<'PY'
import json
from pathlib import Path

from wolframtas_orchestrator.cli import (
    exact_template_to_mathematica_problem,
    materialize_mathematica_problem,
)
from wolframtas_orchestrator.command_parser import command_to_exact_template
from wolframtas_orchestrator.mathematica_script import render_mathematica_script

command = "sj45(12)"
constraints_path = Path("/tmp/wolframtas/constraints.json")
template_out = Path("/tmp/wolframtas/sj45_12_exact_template.json")
json_out = Path("/tmp/wolframtas/sj45_12_mathematica_input.json")
wls_out = Path("/tmp/wolframtas/sj45_12_mathematica_input.wls")

template = command_to_exact_template(
    command,
    objective_axis="z",
    sense="maximize",
    init_speed=0.0,
    init_imux=0.91,
    init_imuz=0.91,
)
template["name"] = "sj45_12_inspection"
template["constraints"] = json.loads(constraints_path.read_text(encoding="utf-8"))
template_out.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")

problem = exact_template_to_mathematica_problem(
    template,
    constraint_tolerance=0.0,
    fill_missing_tolerance=False,
)
problem = materialize_mathematica_problem(problem)

json_out.write_text(json.dumps(problem, indent=2) + "\n", encoding="utf-8")
wls_out.write_text(
    render_mathematica_script(problem, source_name=str(json_out)),
    encoding="utf-8",
)
print(wls_out)
PY
```

Run the rendered script:

```sh
wolframscript -file /tmp/wolframtas/sj45_12_mathematica_input.wls
```

Or run the canonical optimizer from the generated Mathematica JSON:

```sh
wolframscript -file mathematica/optimize.wls /tmp/wolframtas/sj45_12_mathematica_input.json
```

## Strict vs Relaxed Scripts

The staged pipeline solves a strict problem first, then a relaxed problem. To
render the relaxed model instead, change:

```python
problem = exact_template_to_mathematica_problem(
    template,
    constraint_tolerance=0.0,
    fill_missing_tolerance=False,
)
```

to:

```python
problem = exact_template_to_mathematica_problem(
    template,
    constraint_tolerance=0.0001,
    fill_missing_tolerance=True,
)
```

Per-constraint `mathematica_tolerance` values override the default when
`fill_missing_tolerance=True`.

## Slot Numbering

Slots are 1-based. `command_to_exact_template()` adds a leading `init` slot for
bookkeeping, so a command with 12 movement ticks usually has `n = 13`.

Use the generated exact template JSON if you are unsure which slot to constrain:

```sh
jq '.n, .movement_plan.slots[] | {slot, kind, controls, acceleration, retention}' \
  /tmp/wolframtas/sj45_12_exact_template.json
```

For Mathematica positions, use `X[F, slot]` and `Z[F, slot]`. For typed
constraints, use the JSON fields above and let the renderer produce those
expressions.

## Full Pipeline Alternative

If you do not need to inspect the Wolfram script, run the full command pipeline:

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python -m wolframtas_orchestrator \
  solve-command "sj45(12)" \
  --name sj45_12 \
  --constraints-file /tmp/wolframtas/constraints.json \
  --out-dir /tmp/wolframtas/run
```

That writes the exact-solver input, exact solution JSON, and macro CSV, but not
the intermediate Mathematica `.wls`.
