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
built C++ solver (run under `.venv-oracle` — see the Toolchain section):

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python -m pytest e2e
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
- Slime and ice ground retention; cobweb (`web`) ¼ cut + prev-web carry zero;
  ladder (`ladder`) ±0.15 clamp.
- Sneak input scaling; sprint attribute with the air one-tick delay.
- Explicit `wall_hit.axes` retention cancellation per movement slot (no position
  clamp — the optimizer re-anchors coordinates).
- `wall_collision {axis, value}` threshold collision: after the slot's move, if
  the axis crosses the wall coordinate, clamp the position to it and zero that
  axis's velocity (real Minecraft moveEntity clamping). See the command modifier
  `s[hitz=val](1)` below.
- Inertia `hit` and `avoid` residual checks using post-retention velocity
  before threshold zeroing.
- Local discrete repair in 65536 Minecraft angle-index space.

The exact-solution JSON (`states_exact`) exposes both `velocity` (the
pre-retention move velocity) and `retained_velocity` (post-drag, what carries to
the next tick) per state.

Source of truth: the mothball reference simulator. There are NO hardcoded
expected movement values anywhere. `e2e/test_command_parser.py` parses ~37
mothball command strings and asserts the C++ solver matches mothball **bit-exact
on all four components** (`x`, `z`, `vx`, `vz`) — so both travel and
perpendicular drift are pinned to mothball, not to self-generated numbers. The
C++ ctest fixtures assert only solver behaviour mothball cannot express (status,
which constraint failed, repaired angle indices, a residual of exactly 0, or an
axis a wall/threshold zeroes to exactly 0); none encodes a physics magnitude.

## Full-flow command coverage (command -> Wolfram -> exact -> macro)

`solve-command` runs a mothball command through the staged optimizer and exact
solver. These mechanics run to `status: solved` with the exact result matching
mothball bit-for-bit: walk, sprint, walk-jump, sprint-jump, sneak, sneaksprint,
45-strafe, air, water, lava, slime/ice (`setslip`), cobweb, and ladder when the
0.15 clamp does not engage.

- Cobweb is modeled in the Mathematica stage by editing the derived imu/mmu
  (web tick: `mmu *= web_motion_factor`, `imu = 0`; tick before a web:
  `imu *= web_motion_factor`), using the same shared `web_motion_factor` constant
  the C++ solver uses for the real per-tick cut.
- Ladder is intentionally treated as plain air in the Mathematica stage; the
  0.15 clamp lives only in the C++ exact solver. So a ladder command where the
  clamp actually engages (e.g. a sprint-jump onto a ladder) trips the staged
  objective-drift guard and reports `failed`, even though the exact simulation is
  correct. This is a known, accepted optimizer-model approximation gap.

Movement/medium mechanics (walk, sprint, jumps, 45, sneak, sneaksprint, air,
water, lava, slime, ice, ladder, web, sprint delay) are validated by **parsing
mothball command strings and comparing the C++ solver to the mothball simulator
bit-exact on x/z/vx/vz** (`e2e/test_command_parser.py`; ~37 commands, no
hand-authored expected values). This replaced the per-mechanic hand-authored
ctest fixtures.

The solver ctest is a lean set with NO hardcoded physics magnitudes: the C++
unit tests assert only structural invariants (a symmetric 45 input leaves exactly
zero perpendicular drift — the `-ffp-contract=off` guarantee; a wall cancels its
axis to exactly 0), and the fixtures assert only behaviour mothball cannot
express — angle repair, constraint/objective failure, one-axis `wall_hit`, and
the seeded-velocity inertia threshold (`inertia_hit`, `inertia_avoid`) — via
status, the worst constraint id, repaired angle indices, and residuals of
exactly 0.

Building this surfaced a 1-ULP slip bug: fluid slip was computed in float32
(`0.5F / 0.91F`) but mothball computes it in float64 then rounds (`fl(0.5/0.91)`).
Fixed in `solver/src/exact_movement.cpp` and `movement_model.py`; water was
coincidentally unaffected.

## Command parsing (mothball syntax)

`orchestrator/wolframtas_orchestrator/command_parser.py` parses mothball command
strings (e.g. `sj(12)`) into an exact-solver input, by driving the mothball
engine vendored at `orchestrator/vendor/` (with the author's permission, see its
NOTICE.md). The same parse also yields mothball's own simulated final state, so
`e2e/test_command_parser.py` validates the solver against mothball per command
(~46 commands, all bit-exact on x/z/vx/vz). The vendored engine needs numpy 1.26
+ `evalidate`, so that test runs under `.venv-oracle` (see Toolchain below).
Alignment: with the leading init slot (n = 1 + moves), mothball's final position
== `states_exact[n-1].z`, final velocity == `states_exact[n].vz`.

Beyond mothball's own commands, the parser adds two WolframTAS-only conveniences:

- `stop` / `stopair` are mothball's real inputless-tick commands (aliases
  `st` / `sta`); they need no special handling.
- `s[hitx=val](1)` / `s[hitz=val](1)` is a WolframTAS-only wall-collision
  modifier (mothball has no collision). The hit tick crosses the wall at `val`;
  the solver clamps the axis to `val` and zeroes its velocity. mothball can't
  simulate this, so the parser validates it by handing mothball the
  post-collision state directly (`setposz(val) setvz(0)`) instead of simulating
  the hit, then appending one catch-up `stop` so mothball's move-then-accelerate
  order settles the post-wall acceleration into position. With the catch-up,
  mothball's final aligns with the solver's actual last state `states[n]`
  (retained velocity), so `check_command_sim` compares there for wall commands.
  Validated bit-exact for 1D movement straight into the wall; 2D mixed-axis
  (significant motion on the non-walled axis) is a known gap (1-ULP perpendicular
  artifact from the catch-up), and wall sprint removal is not yet wired into this
  modifier.

## Cross-model consistency (single source of truth)

The imu (retention) and mmu (base movement magnitude) constants are now derived
in exactly ONE place: `tools/gen_movement_constants.py` computes them in numpy
float32 (mothball reference semantics, same op order the solver uses) and emits
two committed artifacts:

- `orchestrator/wolframtas_orchestrator/movement_constants.json` (orchestrator/Wolfram)
- `solver/include/wolframtas/movement_constants_generated.hpp` (C++ solver, `constexpr`)

Regenerate after any physics-constant change:
`./.venv-oracle/bin/python tools/gen_movement_constants.py` (needs numpy 1.26).

The C++ solver reads retention + base movement from the generated header (and
does the forward/strafe 2D decomposition + sprint-jump 0.2 boost in `simulate()`).
`movement_model.py` no longer derives physics: it reads the JSON and assembles
the per-tick arrays the Mathematica stage uses (it folds base * input_factor +
boost into a single magnitude, since the Wolfram model wants speed-along-facing
directly). This removed the earlier buggy duplicate derivation — e.g.
`flat_walk` ignored the block medium, and the air-sprint one-tick delay and sneak
input factors were missing on the orchestrator side; all now match the solver.

`e2e/test_movement_model_consistency.py` guards the table two ways: the committed
JSON/HPP must match a fresh run of the generator (no stale artifacts), and the
JSON the orchestrator reads must equal what the compiled solver derives at
runtime (echoed in its `derived_model` block).

## Sprint state

`controls.sprint` is the per-tick sprint ATTRIBUTE (what applies the boost),
distinct from the sprint keyboard input. The solver applies the boost from it:
immediate on ground, delayed one tick in air (previous slot), matching mothball's
`prev_sprint`. The solver does NOT strip sprint on sneak/water/lava/wall; the
plan builder (command parser or optimizer) sets the attribute per tick. Sneaking
removes the keyboard input but not an already-true attribute, and the one-tick
air delay yields the sneaksprint window. The `wall_sprint_cancel` ctest fixture
covers dropping sprint at the wall tick (one no-sprint air slot follows); the
turn-on delay and sneak+sprint (`sprintair`, `sns45`, `sj45`, ...) are covered by
the parser command-parity tests.

## Movement decomposition (faithful mothball port)

The exact solver mimics mothball's real forward/strafe 2D decomposition for all
movement (the old scalar 45 "magnitude along the resultant" shortcut is gone).
`movement_directions[].radians` stays the movement (travel/resultant) direction;
the solver derives the facing (MC yaw) via
`facing = -movement_direction + atan2(strafe, forward)` and uses it for the
decomposition, the angle repair, and the macro YAW column (the significant
angle). For a 45 fixture/command, movement_direction stays the travel direction
and the solver derives the 45° facing; the locked `flat_sprintjump_45` z is
unchanged. The solver compiles with
`-ffp-contract=off` so float32 arithmetic matches numpy bit-exactly (no fused
multiply-add). Mechanics covered and mothball-validated: fluids, inertia
hit/avoid, wall-hit, slime, ladder clamp, cobweb, sprint delay, sneak, sneak-45.

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

## Toolchain (read this before running anything)

The vendored mothball engine is the oracle and needs **numpy 1.26** (NOT 2.x —
NEP50 promotion differs and breaks bit-exact parity) plus `evalidate`. The repo
uses a dedicated virtualenv `.venv-oracle/` for ALL Python (it also has
`pytest`). System pythons here lack pytest and have the wrong numpy, so use
`.venv-oracle/bin/python` for every Python command below.

Setup (one time), using brew's Python 3.10 (its OpenSSL works with the package
index; the system python's LibreSSL does not):

```sh
/opt/homebrew/bin/python3.10 -m venv .venv-oracle
.venv-oracle/bin/pip install "numpy==1.26.*" evalidate pytest
```

Wolfram Engine must be installed and licensed for the e2e tests (real
`wolframscript`). On this Mac the kernel is at
`/Applications/Wolfram.app/Contents/MacOS/WolframKernel`.

Regenerate the shared movement constants after any physics-constant change
(emits the JSON + C++ header; needs numpy 1.26):

```sh
.venv-oracle/bin/python tools/gen_movement_constants.py
```

## Test Commands

Build and run solver tests (no Python env needed beyond a plain `python3` for the
fixture asserter):

```sh
cmake -S solver -B solver/build
cmake --build solver/build
ctest --test-dir solver/build --output-on-failure
```

Run orchestrator unit/component tests:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=orchestrator .venv-oracle/bin/python -B -m pytest orchestrator/tests
```

Run no-mock end-to-end tests (real `wolframscript` + built solver + mothball
oracle; the parity test imports the vendored numpy-1.26 engine):

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python -m pytest e2e
```

Run just the mothball command-parity check (the source-of-truth bit-exact test):

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python e2e/check_command_sim.py
```

## Useful Commands

Full flow from a mothball command (the headline capability: command -> Wolfram
-> exact -> macro):

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python -m wolframtas_orchestrator \
  solve-command "sj45(12)" \
  --macro-out /tmp/wolframtas_macro.csv \
  --solver-command solver/build/wolframtas_solver \
  --exact-out /tmp/wolframtas_exact.json
```

Render an inspectable Wolfram script:

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python -m wolframtas_orchestrator render-mathematica \
  examples/simple_jump/inertia_mathematica_input.json \
  --out /tmp/wolframtas_inertia.wls
```

Run the staged exact flow (from an exact-solver input):

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python -m wolframtas_orchestrator solve-exact-input \
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
