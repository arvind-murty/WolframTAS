# Current Status

This is the handoff snapshot for the current WolframTAS core pipeline.

## Working Pipeline

The project is now input-first for new optimizer work:

```text
movement_plan + typed constraints
-> generated Mathematica input
-> strict Wolfram solve
-> relaxed Wolfram solve
-> generated exact-solver input
-> C++ exact repair/search
-> exact JSON + optional macro CSV
```

The no-mock end-to-end test runs this path with real `wolframscript` and the
built C++ solver:

```sh
python3 -B -m pytest e2e
```

## Main Contracts

- `schemas/optimization_request.schema.json`: user/mod-facing request shape.
  It uses `initial_state`, `movement_plan`, typed `constraints`,
  `inertia_events`, `exact_objective`, and solver settings.
- `schemas/movement_plan.schema.json`: semantic slot inputs. This is the source
  of truth for movement values.
- `schemas/mathematica_input.schema.json`: low-level generated/debug input for
  Wolfram. New hand-authored problems should generally not start here.
- `schemas/exact_solver_input.schema.json`: movement plan plus Mathematica's
  selected `optimal_solution.movement_directions`.
- `schemas/exact_solution.schema.json`: C++ exact solver JSON output.
- `schemas/macro_csv.md`: external macro CSV format.

## Current Exact Solver Support

The exact solver currently supports fixed-tick horizontal movement cases:

- `init` speed slots, decomposed with `std::sin`/`std::cos`.
- Flat ground and air forward movement for no-45 and 45 inputs.
- Water and lava movement/retention for no-45 and 45 forward inputs.
- Explicit `wall_hit.axes` retention cancellation per movement slot.
- Inertia `hit` and `avoid` residual checks using post-retention velocity
  before threshold zeroing.
- Local discrete repair in 65536 Minecraft angle-index space.

Locked exact outputs:

- Flat sprint jump no-45 final `z = 2.6234314852435587`.
- Flat sprint jump 45 final `z = 2.645539114938402`.

## Important Invariants

- Mathematica angle variables are movement directions in radians, not final
  macro yaw degrees.
- Degrees are output-only for diagnostics and macro relative yaw.
- Exact solver derives movement from `movement_plan`; it should not trust
  hand-authored `mmu`/`imu` values.
- `mathematica/optimize.wls` is canonical and should not be changed lightly.
  Ask before changing Wolfram optimizer behavior.
- Exact movement arithmetic and float/double operation order are sensitive.
  Keep the locked outputs unchanged.
- Python-generated Wolfram expressions must use normal decimal notation, not
  scientific notation such as `2e-05`.

## Test Commands

Build and run solver tests:

```sh
cmake -S solver -B solver/build
cmake --build solver/build
ctest --test-dir solver/build --output-on-failure
```

Run orchestrator unit/component tests:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=orchestrator python3 -B -m pytest orchestrator/tests
```

Run no-mock end-to-end tests:

```sh
python3 -B -m pytest e2e
```

## Useful Commands

Render an inspectable Wolfram script:

```sh
PYTHONPATH=orchestrator python3 -m wolframtas_orchestrator render-mathematica \
  examples/simple_jump/inertia_mathematica_input.json \
  --out /tmp/wolframtas_inertia.wls
```

Run the staged exact flow:

```sh
PYTHONPATH=orchestrator python3 -m wolframtas_orchestrator solve-exact-input \
  examples/simple_jump/repair_exact_solver_input.json \
  --strict-out /tmp/wolframtas_strict.json \
  --relaxed-out /tmp/wolframtas_relaxed.json \
  --exact-input-out /tmp/wolframtas_exact_input.json \
  --exact-out /tmp/wolframtas_exact.json \
  --solver-command solver/build/wolframtas_solver
```

Run the C++ solver and write macro CSV:

```sh
solver/build/wolframtas_solver --macro-csv-out /tmp/wolframtas_macro.csv \
  < examples/simple_jump/flat_sprintjump_exact_solver_input.json
```
