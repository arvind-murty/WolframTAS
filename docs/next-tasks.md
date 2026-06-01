# Next Tasks

This is the recommended implementation queue for the next agent/session.

## 1. Add Feature Fixtures

Create small exact-solver fixtures under `examples/simple_jump/` for the newly
supported fixed-tick mechanics:

- water no-45 and water 45
- lava no-45 and lava 45
- one-axis `wall_hit.axes`
- inertia hit
- inertia avoid

Each fixture should have focused constraints and should be added to CTest via
`solver/tests/assert_solver_fixture.py`.

## 2. Extend Exact Movement Carefully

Likely next mechanics:

- slime retention and bounce in exact solver
- ladder clamp handling in exact solver
- sprint delay/removal state propagation instead of manually encoded slots
- richer wall-hit fixtures, still fixed-tick first

Preserve the locked sprint-jump outputs after every movement edit.

## 3. Improve Schema Validation

Current schema validation is partial and test-local. Useful next steps:

- add a small schema validation test runner for examples
- validate `optimization_request.schema.json`, `exact_solver_input.schema.json`,
  and `exact_solution.schema.json`
- keep this dependency-light unless the project explicitly adopts `jsonschema`

## 4. Reduce Legacy Fixture Path

The old no-op fixture path in `orchestrator/wolframtas_orchestrator/cli.py`
still exists for `examples/simple_jump/request.json` and `approx_solution.json`.
It should eventually be replaced or marked as legacy once the mod-facing request
path uses the staged exact flow directly.

## 5. Decide Wolfram Rendering Ownership

There are two related Wolfram paths:

- `mathematica/optimize.wls` builds the model directly from JSON.
- The orchestrator can render an inspectable `.wls` script.

Do not change `mathematica/optimize.wls` casually. If duplicated rendering
logic becomes painful, discuss whether the canonical optimizer should consume
generated `.wls` or whether both paths should share more generated structure.

## 6. Mod-Facing Pipeline

After the core contracts settle further:

- make the mod serialize the new `optimization_request.schema.json`
- call the orchestrator staged flow
- import/render exact macro CSV output
- add world/block extraction only after core solver needs are stable
