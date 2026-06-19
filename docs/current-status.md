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
-> Python solver (mothball-driven simulation)
-> exact JSON + optional macro CSV
```

Staged zero-tolerance behavior is now explicit: when
`solve-exact-input --default-relaxed-tolerance 0.0` is used, the relaxed
Wolfram pass is skipped and `--relaxed-out` is a verbatim copy of strict
Mathematica output (it is no longer replaced with exact-solver output).

The no-mock end-to-end test runs this path with real `wolframscript`
(run under `.venv-oracle` — see the Toolchain section):

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
- `schemas/exact_solution.schema.json`: Python solver JSON output.
- `schemas/macro_csv.md`: external macro CSV format.

## Python Solver

`orchestrator/wolframtas_orchestrator/python_solver.py` drives mothball's
`Player.move()` directly, giving bit-exact Minecraft parity by construction.
Mothball IS the source of truth — no physics is re-implemented. The solver
supports all mechanics mothball supports: all mediums, sneak, sprint delay,
ladder, web, wall_hit, wall_collision, and stop/stopair.

Source of truth: the mothball reference simulator. There are NO hardcoded
expected movement values. `e2e/check_command_sim.py` parses 49 mothball command
strings and asserts the Python solver matches mothball **bit-exact on all four
components** (`x`, `z`, `vx`, `vz`).

The exact-solution JSON (`states_exact`) exposes `velocity` (retained vx/vz
after the tick, same as mothball's final state) and `retained_velocity` (same
value) per state. Position is stored as `player.x + player.vx` to align with
mothball's one-tick bookkeeping offset.

## Full-flow command coverage (command -> Wolfram -> exact -> macro)

`solve-command` runs a mothball command through the staged optimizer and exact
solver. These mechanics run to `status: solved` with the exact result matching
mothball bit-for-bit: walk, sprint, walk-jump, sprint-jump, sneak, sneaksprint,
45-strafe, air, water, lava, slime/ice (`setslip`), cobweb, and ladder when the
0.15 clamp does not engage.

- Cobweb is modeled in the Mathematica stage by editing the derived imu/mmu
  (web tick: `mmu *= web_motion_factor`, `imu = 0`; tick before a web:
  `imu *= web_motion_factor`), using the same shared `web_motion_factor` constant
  the Python solver uses for the real per-tick cut.
- Ladder is intentionally treated as plain air in the Mathematica stage; the
  0.15 clamp lives only in the Python solver. So a ladder command where the
  clamp actually engages (e.g. a sprint-jump onto a ladder) trips the staged
  objective-drift guard and reports `failed`, even though the exact simulation is
  correct. This is a known, accepted optimizer-model approximation gap.

Movement/medium mechanics (walk, sprint, jumps, 45, sneak, sneaksprint, air,
water, lava, slime, ice, ladder, web, sprint delay) are validated by **parsing
mothball command strings and comparing the Python solver to the mothball simulator
bit-exact on x/z/vx/vz** (`e2e/test_command_parser.py`; ~37 commands, no
hand-authored expected values). This replaced the per-mechanic hand-authored
parity tests.

The `e2e/check_command_sim.py` suite covers 49 mothball command strings.
`orchestrator/tests/` covers unit/component tests with no real Wolfram needed.

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
  simulate this directly, so Pass B of the parser runs each tick normally,
  applies the same crossing check, then patches only the blocked axis (position
  clamped to `val`, velocity zeroed) and forces `sprinting=False` for the next
  tick in the mothball reference; Pass A also patches `controls.sprint = false`
  on the appropriate slot in the derived plan. Validated bit-exact for both 1D
  and 2D mixed-axis movement — 30-degree facing regressions in DEFAULT_COMMANDS
  confirm there is no perpendicular artifact (the old "catch-up stop" approach
  was replaced with this direct-patch; that doc note was stale). Sprint removal
  is the plan builder's responsibility; the Python solver does NOT auto-cancel
  because constraints are satisfied with the mmu the plan computed.

## Cross-model consistency (single source of truth)

The imu (retention) and mmu (base movement magnitude) constants are now derived
in exactly ONE place: `tools/gen_movement_constants.py` computes them in numpy
float32 (mothball reference semantics, same op order the solver uses) and emits
two committed artifacts:

- `orchestrator/wolframtas_orchestrator/movement_constants.json` (orchestrator/Wolfram)
- [removed — Python solver reads `movement_constants.json` directly]

Regenerate after any physics-constant change:
`./.venv-oracle/bin/python tools/gen_movement_constants.py` (needs numpy 1.26).

The Python solver reads retention + base movement from the generated header (and
does the forward/strafe 2D decomposition + sprint-jump 0.2 boost in `simulate()`).
`movement_model.py` no longer derives physics: it reads the JSON and assembles
the per-tick arrays the Mathematica stage uses (it folds base * input_factor +
boost into a single magnitude, since the Wolfram model wants speed-along-facing
directly). This removed the earlier buggy duplicate derivation — e.g.
`flat_walk` ignored the block medium, and the air-sprint one-tick delay and sneak
input factors were missing on the orchestrator side; all now match the solver.

`e2e/test_movement_model_consistency.py` guards the table two ways: the committed
JSON must match a fresh run of the generator (no stale artifacts), and the JSON
the orchestrator reads must equal what the Python solver reports in its
`derived_model` block.

## Sprint state

`controls.sprint` is the per-tick sprint ATTRIBUTE (what applies the boost),
distinct from the sprint keyboard input. The solver applies the boost from it:
immediate on ground, delayed one tick in air (previous slot), matching mothball's
`prev_sprint`. The solver does NOT strip sprint on sneak/water/lava/wall; the
plan builder (command parser or optimizer) sets the attribute per tick. Sneaking
removes the keyboard input but not an already-true attribute, and the one-tick
air delay yields the sneaksprint window. The `wall_sprint_cancel` parity test
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
angle). Macro yaw is emitted as relative deltas and repaired/exact movement
slots use midpoint-of-bucket yaw representatives. For a 45 fixture/command,
movement_direction stays the travel direction and the solver derives the 45°
facing; the locked `flat_sprintjump_45` z is
unchanged. The solver compiles with
`-ffp-contract=off` so float32 arithmetic matches numpy bit-exactly (no fused
multiply-add). Mechanics covered and mothball-validated: fluids, inertia
hit/avoid, wall-hit, slime, ladder clamp, cobweb, sprint delay, sneak, sneak-45.

## Block Route Builder

`python3 -m wolframtas_orchestrator solve-block-route input.json --out result.json`
is the one-shot block-route flow. It compiles `schemas/block_route_input.schema.json`,
coarse-scores generated candidates, runs precise staged/exact solving on the
selected candidates, and reports `best_candidate_id`. Inputs should use
`landing_blocks` for the ordered platform route; legacy `blocks` is still
accepted as an alias. The first landing block is the departure/origin block.
`run_ticks` belong to departure landing blocks and produce running overlap
constraints; landing constraints are generated on target landing blocks.
Top-level solid `avoid_blocks` are keyed by `between: [from_landing, to_landing]`;
the builder uses the vertical jump trace to find overlap ticks and emits a
candidate bundle of corner/side schedules because block collision avoidance is
disjunctive. Air slot counts are derived from mothball's vertical jump tick
order, while horizontal arrays are still derived from the generated
`movement_plan`.

`score-block-route` runs a fast Wolfram pass over a route input or generated
candidate bundle. It forces a coarse relaxed tolerance onto all constraints,
uses low optimizer goals by default, ranks candidates by objective, and writes
the selected top/near-best candidates for the later precise staged solve.
`solve-block-route-candidates` then runs the normal strict/relaxed Mathematica
and exact solver flow over the selected candidates and reports `best_candidate_id`
from the final exact outputs. Candidate-level Wolfram/exact failures are recorded
in the result bundle instead of aborting the whole route solve; the bundle status
is `failed` when no candidate completes.
If a strict candidate solve fails but the candidate has a numeric coarse
solution, the precise runner seeds the exact solver from that coarse solution and
marks the candidate `completed_from_coarse`.
`examples/block_route_simple/block_route.json` is a real successful one-shot
smoke fixture. `examples/block_route_demo/block_route.json` includes a solid
avoid block and has a tested feasible north-to-south route-transition candidate.

## Important Invariants

- Mathematica angle variables are movement directions in radians, not final
  macro yaw degrees.
- Degrees are output-only for diagnostics and macro relative yaw. Macro CSV
  columns are `W,A,S,D,P,N,J,YAW,PITCH,L,R,COUNT,H`; `H` is currently emitted as
  `0`.
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
(emits the JSON; needs numpy 1.26):

```sh
.venv-oracle/bin/python tools/gen_movement_constants.py
```

## Test Commands

Run orchestrator unit/component tests:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=orchestrator .venv-oracle/bin/python -B -m pytest orchestrator/tests
```

Run no-mock end-to-end tests (real `wolframscript` + mothball oracle):

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python -m pytest e2e
```

Run just the mothball command-parity check (49 commands, bit-exact):

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python e2e/check_command_sim.py
```

## Useful Commands

Full flow from a mothball command (command -> Wolfram -> Python solver -> macro):

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python -m wolframtas_orchestrator \
  solve-command "sj45(12)" \
  --macro-out /tmp/wolframtas_macro.csv \
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
  examples/p2p_zero_tol_demo/p2p_zero_tol_demo_template.json \
  --strict-out /tmp/wolframtas_strict.json \
  --relaxed-out /tmp/wolframtas_relaxed.json \
  --exact-input-out /tmp/wolframtas_exact_input.json \
  --exact-out /tmp/wolframtas_exact.json
```

Run the Python solver directly on an exact-solver input:

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python - << 'EOF'
import json
from wolframtas_orchestrator.python_solver import solve, write_macro_csv
from pathlib import Path
with open("examples/p2p_zero_tol_demo/p2p_zero_tol_demo_exact_input.json") as f:
    inp = json.load(f)
sol = solve(inp)
Path("/tmp/exact_solution.json").write_text(json.dumps(sol, indent=2))
write_macro_csv(Path("/tmp/macro.csv"), sol)
EOF
```
