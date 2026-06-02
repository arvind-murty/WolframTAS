# WolframTAS Agent Notes

WolframTAS is a Forge 1.8.9 Minecraft client mod for optimizing parkour routes.

Use this file as persistent project context for Codex. Keep it short and update
it whenever stable technical decisions change.

For a compact handoff snapshot, read `docs/current-status.md`. For the next
recommended implementation queue, read `docs/next-tasks.md`.

## Core Pipeline

1. A low-level Mathematica input JSON describes `Imux`, `Imuz`, `Mmu`, constants,
   constraints, objective, component overrides, and inertia events.
2. Python orchestrator can render that schema into an inspectable `.wls` script
   and can run the canonical Wolfram optimizer.
3. Mathematica emits approximate movement-direction angles as JSON.
4. Python combines fixed movement-plan inputs with Mathematica angles and passes
   them to the C++ exact solver.
5. C++ produces exact solution JSON and can write macro CSV with
   `--macro-csv-out`.

The Forge mod is a later quality-of-life client for creating problem
definitions, starting the orchestrator, and optionally rendering results. Do not
let mod concerns drive the core contracts.

## Stable Decisions

- Minecraft mod loader: Forge.
- Project name: WolframTAS. The old WolfTAS name/path is obsolete and should
  not be reintroduced in docs, package names, schemas, or commands.
- Minecraft version: 1.8.9.
- Mod language: Java.
- Java compatibility: Java 8.
- Gradle wrapper: Gradle 2.14.1 for legacy ForgeGradle compatibility.
- macOS ARM note: ForgeGradle must run with Java 8. The repo `./gradlew`
  launcher auto-selects `/usr/libexec/java_home -v 1.8` when `JAVA_HOME` is not
  set.
- The wrapper sets `GRADLE_USER_HOME` to `.gradle-user-home` and
  `-Dorg.gradle.native=false`; both are intentional for reliable local runs on
  modern macOS ARM.
- User-confirmed Wolfram command-line workflow:
  `wolframscript -file examples/mathematica_sim.wls`.
- Codex should run `wolframscript` commands unsandboxed when verification is
  needed; sandboxed runs may not see the Wolfram kernel configuration.
- If unsandboxed `wolframscript` cannot find the kernel, use
  `/Applications/Wolfram.app/Contents/MacOS/WolframKernel` explicitly or check
  `wolframscript -configure`.
- Angle domain: Minecraft discrete lookup table of size `2^16`.
- Mathematica input v1 is `schemas/mathematica_input.schema.json`: a low-level
  Mathematica-ready JSON contract with direct `Imux`, `Imuz`, `Mmu`, constants,
  expression-string constraints/objective, explicit component overrides, and
  inertia events.
- `mathematica/optimize.wls` is the canonical CLI optimizer entrypoint:
  `wolframscript -file mathematica/optimize.wls path/to/input.json`. It prints a
  single RawJSON approximate solution object to stdout.
- Schema-to-Wolfram rendering belongs to the Python orchestrator, currently via
  `python3 -m wolframtas_orchestrator render-mathematica`. Do not create random
  one-off generator scripts; add reusable code under `orchestrator/` instead.
- The Python orchestrator can run Mathematica via
  `python3 -m wolframtas_orchestrator run-mathematica input.json --approx-out out.json`.
- Exact-solver input v1 is `schemas/exact_solver_input.schema.json`: an
  input-first solver-ready JSON contract with `movement_plan`, `initial_state`,
  and Mathematica's selected `optimal_solution.movement_directions`. Low-level
  `Imux`, `Imuz`, and `Mmu` arrays belong in generated/debug `derived_model`
  data or legacy fixtures, not new hand-authored exact-solver inputs.
- The C++ solver consumes exact-solver input JSON on stdin, derives supported
  forward-only movement values from `movement_plan`, and simulates from the
  selected movement direction.
- The imu (retention) and mmu (base movement) constants have a SINGLE source of
  truth: `tools/gen_movement_constants.py` computes them in numpy float32 and
  emits `orchestrator/wolframtas_orchestrator/movement_constants.json` (read by
  the orchestrator) and `solver/include/wolframtas/movement_constants_generated.hpp`
  (a `constexpr` table compiled into the solver). Both committed artifacts are
  generated; regenerate with the tool (numpy 1.26) after any constant change and
  rebuild the solver. Do not re-derive these constants inline in either component.
- Exact solver angle handling: keep Mathematica movement directions in radians
  internally and flip sign to get Minecraft yaw radians. Apply Minecraft-style
  float32 angle indexing for `mcsin`/`mccos`
  (`(int)(value * 10430.378F)` and cosine `+ 16384.0F`, masked with `65535`),
  but compute the indexed sine value with `std::sin` on demand instead of
  caching a 65536-float table. Convert to degrees only for exact-solution
  diagnostics and macro-relative yaw output.
- Exact solver horizontal state currently uses double/float64 `x`, `z`, `vx`,
  and `vz` to match anon-noob mothball `player.py` under NumPy 1.26 scalar
  promotion. Movement-plan inputs derive acceleration/retention through the
  same float32 movement-intermediate paths before simulation.
- Exact solver v1 supports fixed water/lava acceleration and retention for
  no-45/45 forward inputs, explicit `wall_hit.axes` retention cancellation, and
  inertia hit/avoid residual checks against post-retention velocity before the
  normal `0.005` threshold zeroing.
- Macro CSV details are documented in `schemas/macro_csv.md`. The external
  format columns are `W,A,S,D,P,N,J,YAW,PITCH,L,R,COUNT`; yaw and pitch are
  relative degree deltas, not absolute angles. The C++ solver writes the CSV
  with `--macro-csv-out`.
- Python has a first staged exact handoff command:
  `python3 -m wolframtas_orchestrator solve-exact-input ...`. It derives
  Mathematica arrays from `movement_plan`, runs strict and relaxed Mathematica
  solves, checks objective drift, writes the generated exact input, and invokes
  the C++ exact solver.

## Engineering Rules

- Prefer explicit contracts at component boundaries, but do not invent contract
  fields before the required Mathematica/solver/macro details are provided.
- Keep fixtures in `examples/` small and human-readable.
- When changing cross-component behavior, update schemas, examples, and tests
  in the same change.
- Generated inspection scripts in `examples/` must be reproducible through the
  orchestrator renderer; keep the source JSON fixture next to them.
- Do not commit generated outputs, build directories, IDE metadata, or logs.
- Avoid repo-wide refactors unless they are required for the current task.

## Component Boundaries

- `mod/`: later GUI, world/block extraction, request serialization, macro
  import/export, optional render overlay.
- `orchestrator/`: process execution, stdin/stdout/file handoff, logging, and
  validation of pipeline artifacts. It also owns rendering the Mathematica input
  schema into inspectable/runnable Wolfram scripts and invoking the canonical
  Wolfram optimizer. It also owns the mothball command parser:
  `command_parser.py` drives the mothball engine vendored at
  `orchestrator/vendor/` (parser + simulator, used with the author's permission;
  see its NOTICE.md) to turn command strings like `sj(12)` into an exact-solver
  input plus mothball's reference final state. The vendored engine needs numpy
  1.26 + `evalidate`. Do not edit the vendored files; adapt their output in
  `command_parser.py` (original code).
- `mathematica/`: approximate continuous optimization.
- `solver/`: exact movement conversion and macro CSV output.
- `schemas/`: source of truth for shared data formats once finalized.

## Current Useful Commands

- Render a schema fixture to an inspectable Wolfram script:
  `PYTHONPATH=orchestrator python3 -m wolframtas_orchestrator render-mathematica examples/involved_mathematica_input.json --out examples/involved_from_schema.wls`
- Run Mathematica through the orchestrator:
  `PYTHONPATH=orchestrator python3 -m wolframtas_orchestrator run-mathematica examples/simple_jump/inertia_mathematica_input.json --approx-out /tmp/wolframtas_inertia_approx.json`
- Run the canonical Wolfram optimizer directly:
  `wolframscript -file mathematica/optimize.wls examples/simple_jump/inertia_mathematica_input.json`
- Run orchestrator tests:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=orchestrator python3 -B -m pytest orchestrator/tests`
- Run no-mock end-to-end tests with real Wolfram and the built C++ solver:
  `python3 -B -m pytest e2e`

## Current Fixtures

- `examples/simple_jump/mathematica_input.json`: simple water-transition optimizer fixture.
- `examples/simple_jump/wall_ladder_mathematica_input.json`: separated `Imux`/`Imuz` plus ladder-style component override.
- `examples/simple_jump/inertia_mathematica_input.json`: inertia hit and inertia avoid fixture.
- `examples/simple_jump/flat_sprintjump_exact_solver_input.json`: input-first exact-solver fixture for flat sprintjump no-45, used to check the solver's NumPy-1.26-style horizontal recurrence.
- `examples/involved_sim.wls`: user-provided larger handwritten Wolfram example.
- `examples/involved_mathematica_input.json`: JSON port of the involved example.
- `examples/involved_from_schema.wls`: generated inspection script from the JSON port.

## Next Unfinished Work

- Add focused exact-solver fixtures for water/lava, wall-hit, and inertia paths.
- Reduce or remove the legacy fixture/no-op exact-solution path once the
  mod-facing request flow uses staged solving directly.
- Decide whether `mathematica/optimize.wls` should continue building directly from JSON or consume generated `.wls` from the orchestrator to avoid duplicated Wolfram model rendering logic.

## Learned Movement Rules

- Mathematica angle variables currently represent movement direction, not
  Minecraft yaw/facing. Yaw conversion/sign flipping is a later step.
- `Mmu` stores per-slot horizontal acceleration magnitudes, plus `init` when
  chaining previous momentum into the same closed-form contribution model.
- `Imux`/`Imuz` store per-slot horizontal velocity retention/drag multipliers.
- Chained simulations assume the first `init` slot moves from tick 0 to tick 1.
  In movement-plan inputs, `kind: "init"` is an authoritative horizontal
  speed contribution with explicit `speed`, `imux`, and `imuz`; it is not
  validated against keyboard movement. The speed is used as the first `Mmu`
  entry, and the direction is represented by the first movement-direction angle.
  The exact solver decomposes init speed with ordinary `std::sin`/`std::cos`,
  not Minecraft `mcsin`/`mccos`.
- Air drag is `0.91`. Flat normal-ground drag after a ground tick is
  `0.91 * 0.6 = 0.546`. Water drag is `0.8`.
- No-45 forward movement uses the `0.98` input factor. 45-strafe uses `1.0`.
- Sprint multiplier is `1.3` when applicable.
- Flat-ground walk jump, no 45: `0.1 * 0.98 = 0.098`.
- Flat-ground sprint jump, no 45, when sprint is active on the jump tick:
  `0.1 * 1.3 * 0.98 + 0.2 = 0.3274`.
- Air no-45 walking acceleration: `0.02 * 0.98 = 0.0196`.
- Air no-45 sprint acceleration: `0.02 * 1.3 * 0.98 = 0.02548`.
- Water/lava have 45/no-45 input behavior, but no normal sustained sprinting.
- Water, lava, sneaking, and hitting a wall remove sprint.
- Exact-solver movement-plan slots separate acceleration context from retention
  context so fixed-tick edge cases can override drag provenance without
  changing the acceleration path.
- Distinguish the sprint KEYBOARD INPUT from the sprint ATTRIBUTE. The attribute
  is what applies the speed boost (mothball's `sprinting` arg). `controls.sprint`
  in a movement slot is the attribute for that tick.
- The solver applies the boost from `controls.sprint`: immediate on the current
  tick on ground; delayed by one tick in air (uses the previous slot's
  `controls.sprint`), matching mothball's `prev_sprint`. The solver does NOT
  strip sprint for sneak/water/lava/wall — water/lava simply take the no-boost
  acceleration branch, and whoever builds the plan (the command parser mirroring
  mothball, or the optimizer) sets the attribute per tick.
- Sneaking removes the sprint KEYBOARD INPUT, but it does not override an
  already-true sprint attribute. Because air sprint activation/removal is delayed
  one tick, the attribute can stay true for one air tick after sneaking starts —
  the `sneaksprint` tech. The solver reproduces this through the one-tick air
  delay: set `controls.sprint` false from the tick the keyboard is removed, and
  the previous (true) attribute still boosts that one air tick. mothball's
  `sneaksprint` command instead holds the attribute true while sneaking
  (sustained), which the solver also matches since it uses `controls.sprint`
  directly. (Likewise a one-tick air wall hit: drop `controls.sprint` at the wall
  tick; that tick is still boosted via the delay, then exactly one no-sprint air
  slot follows, then sprint can resume.) Validated bit-exact vs mothball,
  including the parser commands `s45`/`sns45`/`sj45`. `derive_arrays_from_movement_plan`
  (`slot_effective_sprint`) just reads `controls.sprint`.
- Slime block slipperiness is `0.8`, so horizontal ground drag on slime is
  `0.91 * 0.8 = 0.728`.
- Falling on slime inverts negative vertical speed unless sneak/jump cancels
  the bounce. In the flat sprint-jump-to-slime example, the raw inverted bounce
  speed is about `0.447497867013`; after the same tick's gravity/drag, the next
  stored vertical speed is about `0.360147909673`.
- For chained `init` -> flat sprint jump -> slime bounce -> flat landing, the
  post-bounce landing-condition tick is `n = 22`. Slot 23 can still be simulated
  as the extra chained state.
- Wall collisions are modeled in Mathematica by fixing a wall-hit tick and
  shifting coordinates after that tick instead of fully modeling collision
  geometry in the recurrence.
- For a wall at constant X, determine contact center from approach side using
  player half-width `0.3`: from west, `xwall = wallX - 0.3`; from east,
  `xwall = wallX + 0.3`.
- A fixed wall-hit tick `m1` can be constrained against the real map coordinate,
  e.g. `X[F, m1] >= xwall - xoff` when approaching from west.
- After wall hit, constrain later X positions relative to the wall-clamped
  coordinate: `xwall + (X[F, m2] - X[F, m1])`.
- To cancel blocked-axis velocity, separate `Imux` and `Imuz`; for an X wall set
  `Imux[[m1]] = 0` while leaving `Imuz` unchanged. This keeps Z momentum.
- When holding sprint and hitting an X wall for one airborne tick, wall sprint
  removal causes exactly one no-sprint air slot after the delayed wall-sprint
  tick, then sprint can resume if no longer hitting the wall.
- For one-tick X wall hit at `m1 = 5` during a flat sprint jump no 45 from
  chained `init`, a typical no-45 `Mmu` pattern is
  `Join[{init, 0.3274}, ConstantArray[0.02548, 4], {0.0196}, ConstantArray[0.02548, 6]]`.
- Landing block overlap constraints use player-center overlap. For a block
  spanning `[b, b+1]`, the overlap range for the player center is
  `[b - 0.3, b + 1.3]`. When an objective pushes toward one side, the opposite
  bound can often be omitted for a simpler example.
- Ladders have a thin `0.125b` physical collision box in 1.8.9, but ladder
  movement effects use a separate climbable/restricted movement voxel.
- The ladder voxel is `1x1x1` in coordinate space for the ladder block, except
  along the mounted axis. Along the mounted axis, the player-coordinate interval
  is either `.0 -> .575` or `.425 -> 1.0`, depending on which side the ladder is
  placed on.
- While inside the ladder voxel, horizontal X/Z speeds are capped at `0.15 b/t`;
  holding sneak/shift prevents falling.
- Ladder horizontal clamps are modeled in Mathematica with fixed tick/axis
  overrides rather than a symbolic `Clip`: hardcode `Mmux` or `Mmuz` for that
  tick to `+/-0.15` and set the corresponding `Imux[[tick]]` or `Imuz[[tick]]`
  to `0` to cancel prior momentum on that axis.
- The sign of the ladder override matters and should match the clamped movement
  direction. The exact ladder clamp belongs in the C++ exact solver; Mathematica
  uses this fixed-tick approximation to preserve the closed-form model.
- The C++ exact solver now implements the ladder clamp directly: a slot with
  `"ladder": true` clamps `vx`/`vz` to `[-0.15, 0.15]` at the Minecraft point
  (after acceleration, before the position move). Validated bit-exact vs mothball.
- Cobweb: a slot with `"web": true` cuts motion to 1/4 that tick (at the same
  pre-move point), and being in web zeroes the carried velocity at the START of
  the next tick (before that tick's acceleration), freezing position. This
  matches mothball's `prev_web` behaviour and is validated bit-exact.
- Sneak: scales the forward/strafe input by 0.3 before the 0.98 factor
  (immediate in 1.8.9; mothball `sneak_delay` is False). It removes the sprint
  KEYBOARD INPUT, but the sprint attribute is handled separately (see the
  keyboard-vs-attribute note above) — the solver does not zero sprint on sneak.
  Validated bit-exact via the parser command-parity tests (`sn`, `sn45`, `sns45`).
- The exact solver mimics mothball's real forward/strafe 2D decomposition for
  ALL movement (the old scalar "magnitude along the resultant" 45 shortcut was
  removed). 45 = forward+strafe inputs rotated by the facing yaw.
  `optimal_solution.movement_directions[].radians` stays the movement
  (travel/resultant) direction, consistent with Mathematica and the rest of the
  pipeline. The solver DERIVES the facing (MC yaw) in `seed_yaw_indices`:
  `facing = -movement_direction + atan2(strafe, forward)` — the negate is the
  convention flip, the atan2 is the travel-vs-facing geometry (0 for forward,
  +/-45 deg for W+A/W+D). The derived facing yaw_index is what the repair tunes
  and what the macro YAW column records (the significant angle), so it must be
  accurate. no-45 keeps facing = travel. `mmu` in the derived arrays is the base
  movement magnitude M; simulate() applies the forward/strafe scaling and the
  separate sprint-jump 0.2 boost. No orchestrator resultant->facing conversion is
  needed.
- The solver compiles with `-ffp-contract=off`. numpy never fuses multiply-add,
  and a fused `strafe*cos - forward*sin` computes one product at extended
  precision, breaking the exact cancellation that makes a symmetric 45 input
  produce zero perpendicular drift. Keep this flag for bit-exact float32 parity.
- mothball and Minecraft match EXACTLY; mothball just reports position one tick
  before the final (velocity is tick N-1 -> N). The C++ solver uses real-MC tick
  order (accel -> move -> drag) and reproduces mothball when initial conditions
  correspond. When validating against mothball, build velocity from rest; do NOT
  seed a raw velocity (it bypasses mothball's clamp/drag and gives a false
  mismatch).
- Momentum threshold is checked independently for X/Z components at the end of
  a tick after slipperiness. In 1.8.9 the threshold is `0.005`; below-threshold
  components are set to `0`.
- Model an inertia-hit tick for one specified axis with two linear
  post-retention upper-bound constraints, e.g. `imu*(X[F,m]-X[F,m-1]) <= 0.005`
  and `imu*(X[F,m-1]-X[F,m]) <= 0.005`, then set the corresponding
  `Imux[[m]]` or `Imuz[[m]]` to `0`.
- Model an inertia-avoid tick for one specified axis and direction with one
  post-retention lower-bound constraint, e.g. positive X uses
  `imu*(X[F,m]-X[F,m-1]) >= 0.005`; negative X flips the subtraction. Do not
  zero `Imux`/`Imuz` for avoid events.
