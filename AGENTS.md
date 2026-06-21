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
   them to the Python solver.
5. Python solver (`python_solver.py`) drives mothball directly, produces
   exact solution JSON and macro CSV.

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
  single RawJSON approximate solution object to stdout. It honors
  `optimizer.accuracy_goal`, `precision_goal`, `working_precision`,
  `max_iterations`, and `method`.
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
- The Python solver consumes exact-solver input JSON on stdin, derives supported
  forward-only movement values from `movement_plan`, and simulates from the
  selected movement direction.
- The imu (retention) and mmu (base movement) constants have a SINGLE source of
  truth: `tools/gen_movement_constants.py` computes them in numpy float32 and
  emits `orchestrator/wolframtas_orchestrator/movement_constants.json` (read by
  the orchestrator and Python solver). Regenerate with the tool (numpy 1.26)
  after any constant change. Do not re-derive these constants inline.
- Python solver angle handling: convert Mathematica movement directions to facing
  angle (degrees) via `facing = -degrees(mv_rad_normalized) + degrees(atan2(strafe, forward))`,
  pass to mothball as `rotation`. Mothball applies Minecraft's float32 angle
  indexing (`(int)(value * 10430.378F) & 65535`) natively. Macro yaw uses
  midpoint-of-bucket formula `(yaw_idx + 0.5) * 360/65536` for float32 tolerance.
- Minecraft has NO angle normalization. The movement pipeline uses raw float32
  truncation (`(int)(value * 10430.378F) & 65535`) with no modulo or remainder.
  mothball matches Minecraft exactly and is the source of truth for all angle
  and movement physics. Never apply `std::remainder` or any wrap to angles
  originating from Minecraft's system. It IS acceptable to normalize Mathematica
  output angles before the float32 cast (e.g. in `python_solver.py`) because
  Mathematica can emit unwrapped values like -6390° meaning 90°; this normalizes
  the optimizer output, not a Minecraft value.
- The Python solver uses mothball's `Player.move()` natively for all movement
  physics. Position, velocity, and retention all follow mothball's float32
  semantics (numpy 1.26). All mediums, sneak, sprint, ladder, web, wall_hit,
  and wall_collision are handled directly by mothball.
- Macro CSV details are documented in `schemas/macro_csv.md`. The external
  format columns are `W,A,S,D,P,N,J,YAW,PITCH,L,R,COUNT,H`; yaw and pitch are
  relative degree deltas, not absolute angles, and `H` is currently always `0`.
  `python_solver.write_macro_csv()` writes the CSV.
- Python has a first staged exact handoff command:
  `python3 -m wolframtas_orchestrator solve-exact-input ...`. It derives
  Mathematica arrays from `movement_plan`, runs strict and relaxed Mathematica
  solves, checks objective drift, writes the generated exact input, and invokes
  the Python solver.
- High-level block-route authoring is `schemas/block_route_input.schema.json`
  and `python3 -m wolframtas_orchestrator build-block-route ...`. It compiles an
  ordered `landing_blocks` list into the existing exact-template shape.
  `run_ticks` belong to the departure landing block and generate running overlap
  constraints; landing constraints are generated on target landing blocks. Solid
  `avoid_blocks` are separate top-level blocks keyed by `between: [from, to]`;
  they use mothball vertical trace overlap and enumerate per-tick/corner side
  schedules into candidate bundles of ordinary conjunctive `position_bounds`.
  `score-block-route` runs a cheap Wolfram pass over a route or candidate bundle
  and writes ranked/selected candidates for the later precise staged solve.
  `solve-block-route-candidates` runs strict/relaxed Mathematica plus exact
  solving over selected candidates and reports the best exact candidate.
  `solve-block-route` chains build, score, and precise solve as the normal
  end-to-end route command.
  Air slot counts are computed from mothball's vertical jump tick order;
  `Imux`/`Imuz`/`Mmu` are still derived from the generated `movement_plan`.
- Zero-relaxed-tolerance semantics for `solve-exact-input`: when
  `default_relaxed_tolerance == 0.0`, the relaxed Wolfram run is skipped and
  `--relaxed-out` is written as a verbatim copy of strict Mathematica output
  (not exact-solver output).

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
- Run orchestrator tests (use `.venv-oracle`; see docs/current-status.md Toolchain):
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=orchestrator .venv-oracle/bin/python -B -m pytest orchestrator/tests`
- Run no-mock end-to-end tests with real Wolfram and the built Python solver:
  `PYTHONPATH=orchestrator .venv-oracle/bin/python -m pytest e2e`

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
  The exact solver decomposes init speed with Python `math.sin`/`math.cos`,
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
- Water/lava/sneak/wall do NOT remove the sprint ATTRIBUTE in the solver (it just
  reads `controls.sprint`); water/lava take the no-boost acceleration branch, and
  the PLAN BUILDER drops `controls.sprint` where a wall/sneak should (see the
  keyboard-vs-attribute note below). In real gameplay these stop sprinting, but
  the solver models that via the per-tick attribute, not by stripping it.
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
- The exact solver also has a direct threshold-collision model separate from the
  `wall_hit.axes` retention trick: a slot's `wall_collision {axis, value}` makes
  `simulate()` clamp the axis position to `value` and zero that axis's velocity
  when the move crosses it. The command parser exposes it as `s[hitx=val](1)` /
  `s[hitz=val](1)`. Because mothball has no collision, Pass B of the parser runs
  each tick normally, then patches only the blocked axis (position clamped to
  `val`, velocity zeroed) and forces `sprinting=False` for the next tick in the
  mothball reference; it also patches `controls.sprint = false` on the
  appropriate slot in the derived plan (Pass A). Validated bit-exact for both 1D
  and 2D mixed-axis movement (30-degree facing regressions in DEFAULT_COMMANDS
  confirm no perpendicular artifact). Sprint removal is the plan builder's
  responsibility: the solver does NOT auto-cancel sprint on crossing because
  constraints are satisfied with the mmu the plan builder computed.
- `stop`/`stopair` (mothball aliases `st`/`sta`) are inputless coast ticks and
  flow through the parser unchanged.
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
  direction. The exact ladder clamp belongs in the Python solver; Mathematica
  uses this fixed-tick approximation to preserve the closed-form model.
- The Python solver now implements the ladder clamp directly: a slot with
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
- Repair semantics are output-defining: when the exact solver changes yaw indices
  to satisfy constraints/objective, those repaired indices are used for BOTH
  constraint evaluation and the FINAL simulated path/output (`states_exact`,
  macro yaw deltas, and diagnostics). Repaired indices are not diagnostics-only.
- Exact-solver constraint math for `position_delta_bound`/`position_bounds` is
  strict (`exact_tolerance` defaults to `0`). Any remaining shortfall in a
  `failed` result is currently a repair-search/budget outcome (local search can
  stop before finding a feasible index set with default settings), not a relaxed
  acceptance path.
- Exact repair keeps each yaw index within two table indices of the Mathematica
  seed by default. If single-slot beam search stalls, it tries deterministic
  contiguous compound windows so several adjacent ticks can move together while
  preserving the same per-tick +/-2 cap.
- The solver compiles with `-ffp-contract=off`. numpy never fuses multiply-add,
  and a fused `strafe*cos - forward*sin` computes one product at extended
  precision, breaking the exact cancellation that makes a symmetric 45 input
  produce zero perpendicular drift. Keep this flag for bit-exact float32 parity.
- mothball and Minecraft match EXACTLY; mothball just reports position one tick
  before the final (velocity is tick N-1 -> N). The Python solver uses real-MC tick
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
