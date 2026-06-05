# Next Tasks

This is the recommended implementation queue for the next agent/session.

## Current open work (top of queue, as of the latest commits)

Recently completed: single-source movement constants table, cobweb Mathematica
model, test suite rewritten to compare bit-exact vs mothball, `stop`/`stopair`
parity, `s[hitx=val]`/`s[hitz=val]` wall-collision modifier. 2D mixed-axis wall
validation confirmed working (the old "catch-up stop" note in the docs was stale;
Pass B now patches the crossed axis directly — see below).

Open, roughly in order:

1. Exact-solver repair robustness for hard constraints: default bounded search
   can return `status: failed` with small x/z shortfall even though a feasible
   repaired index set exists under larger search settings. Decide and implement
   policy (better default budgets, adaptive widening/retry, or deterministic
   fallback search) and add a regression fixture mirroring this behavior.
2. Wall sprint removal: the plan builder (command parser / Mathematica output)
   sets `controls.sprint` per slot; `wall_collision` sprint cancellation is NOT
   auto-applied in the solver because constraints are satisfied with the mmu the
   plan builder computed. If a hand-authored input needs sprint cancellation,
   clear `controls.sprint` on the appropriate slot explicitly.
3. The rest of this file (schema validation, legacy fixture path, Wolfram
   rendering ownership, mod-facing pipeline) is still open and unchanged.
4. Push the local commits (`git push`) — several commits are ahead of origin.

The detailed historical checklist follows.

## 0. Command parsing (DONE)

The mothball command parser is integrated: the engine is vendored at
`orchestrator/vendor/` (with the author's permission) and
`orchestrator/wolframtas_orchestrator/command_parser.py` turns command strings
(`sj(12)`, `walk`, `sprint`, `wj`, ...) into an exact-solver input plus
mothball's reference final state. `e2e/test_command_parser.py` validates several
commands bit-exact through the solver. Open follow-ups: generalize rotation/angle
handling (currently exact for rotation-0 commands; angled commands need the
facing-index round-trip checked), and broaden the slip->retention map and command
coverage as needed.

## 1. Add Feature Fixtures

NOTE (superseded): the per-mechanic movement/medium fixtures below were later
replaced by parser command-parity tests (`e2e/test_command_parser.py`), which
parse mothball commands and compare the solver to the mothball simulator. The
standalone `water/lava/slime/ladder/web/sneak/sprint_turn_on` JSON fixtures were
removed; `wall_hit_x`, `inertia_hit`, `inertia_avoid` remain (no mothball-command
equivalent). The historical checklist is kept below for context.

Originally: create small exact-solver fixtures under `examples/simple_jump/` for
the newly supported fixed-tick mechanics:

- [x] water no-45 and water 45 (now parser commands `walkair(..,water=true)` etc.)
- [x] lava no-45 and lava 45 (now parser commands)
- [x] one-axis `wall_hit.axes` (`wall_hit_x_*`, kept)
- [x] inertia hit (`inertia_hit_*`, kept)
- [x] inertia avoid (`inertia_avoid_*`, kept)

All seven are wired into CTest via `solver/tests/assert_solver_fixture.py`
(16 tests total, all green).

Expected values are blessed against the mothball reference simulator
(`player.py` under numpy 1.26); see the oracle notes in project memory. Notes on
what each fixture validates:

- Fluid + inertia hit/avoid: final state verified bit-exact against mothball.
  The fluid fixtures surfaced and fixed a 1-ULP lava slip bug (float32 vs
  float64 division) in both `solver/src/exact_movement.cpp` and
  `orchestrator/.../movement_model.py`.
- Inertia uses `inertia_events` as feasibility constraints on the post-retention
  (pre-threshold) velocity at a slot: `hit` requires `|v| <= threshold`, `avoid`
  requires the velocity stays past `±threshold`. `simulate()` always applies the
  0.005 per-axis zeroing.
- `wall_hit` cancels momentum on one axis via separated `imux`/`imuz`. Mothball
  uses a single isotropic slip and cannot independently reproduce one-axis
  cancellation, so only the non-wall (Z) axis is mothball-validated; the X freeze
  is a collision model override (matches real-MC: collision zeros that axis).
  NOTE: automatic sprint-cancel-on-wall (1 tick, delayed in air) is NOT yet a
  solver feature — sprint is still encoded manually per slot. That belongs with
  the sprint-state-propagation work in section 2 below.

## 2. Extend Exact Movement Carefully

Likely next mechanics:

- [x] slime retention in exact solver (`0.728` horizontal drag, fixture
  `slime_walk_*`). Bounce is vertical and OUT OF SCOPE: vertical motion is the
  player's fixed input that sets tick counts; the solver is horizontal-only.
- [x] ladder clamp handling in exact solver (`±0.15` horizontal clamp at the MC
  point: after accel, before the move). Fixture `ladder_clamp_*`. Validated
  bit-exact vs mothball from rest. NOTE: mothball and MC match exactly; the C++
  (MC order: accel→move→drag) reproduces mothball when initial conditions
  correspond (validate from rest, never from a raw seeded velocity).
- [x] web (cobweb) handling: motion `/4` the web tick + the prev-web carried
  velocity is zeroed at the START of the next tick (before accel), freezing
  position. Fixture `web_*`. Validated bit-exact vs mothball.
- [x] sprint delay/removal state propagation instead of manually encoded slots
  (done: `slot_effective_sprint` + air 1-tick delay in `exact_movement.cpp`;
  fixtures `sprint_turn_on_air_*`, `wall_sprint_cancel_*`). Fixtures now specify
  the held sprint key; the solver derives effective sprint and the air delay.
- [x] sneak movement scaling (no-45 and 45): sneak scales forward/strafe by 0.3
  before the 0.98 factor (immediate in 1.8.9) and removes the sprint keyboard
  input (NOT the sprint attribute — see the correction note below). Fixtures
  `sneak_walk_*`, `sneak_45_*`, validated bit-exact vs mothball.
- [x] Replaced the scalar 45 shortcut with mothball's real forward/strafe 2D
  decomposition. `movement_directions[].radians` stays the travel/resultant
  direction; the solver derives the facing (MC yaw) =
  `-movement_direction + atan2(strafe, forward)` and uses it for decomposition,
  repair, and the macro YAW (significant angle). Solver compiles
  `-ffp-contract=off` for float32 parity. All 45 fixtures re-validated; locked 45
  z unchanged. No orchestrator resultant->facing conversion needed.
- [ ] richer wall-hit fixtures, still fixed-tick first

After every movement edit, re-run the mothball command-parity test
(`e2e/test_command_parser.py`) — it is the source of truth and must stay
bit-exact on x/z/vx/vz. Do not reintroduce hardcoded expected movement values.

NOTE (correction): the solver does NOT auto-cancel sprint on a wall. Sprint is an
attribute the PLAN BUILDER sets per slot (`slot_effective_sprint` just reads
`controls.sprint`); the command parser/optimizer drops it at a wall tick, and the
air one-tick delay then yields exactly one no-sprint air slot. Sneak scales the
forward/strafe input by 0.3 but does NOT zero the sprint attribute.

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
