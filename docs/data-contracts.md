# Data Contracts

This file tracks contract boundaries, not final field definitions. The exact
schemas should be filled in only after the Mathematica requirements, exact
solver requirements, and existing macro CSV format are known.

## Mathematica Input

Produced by the Python orchestrator from a movement plan, or hand-authored only
for low-level/debug fixtures. Consumed by Mathematica.

The Python orchestrator is responsible for rendering this schema into an
inspectable/runnable Wolfram script when needed. Do not maintain separate
one-off schema conversion scripts.

Schema: `schemas/mathematica_input.schema.json`

Status: v1 low-level generated/debug contract.

This contract is Mathematica-ready rather than gameplay-event based. It stores
the numeric arrays and expressions that the optimizer should use directly. For
new route definitions, prefer the movement plan contract and let the
orchestrator derive these arrays:

- `n`: number of optimized movement-direction slots.
- `arrays.imux`, `arrays.imuz`: horizontal velocity retention multipliers.
- `arrays.mmu`: horizontal acceleration magnitudes, including `init` when chaining.
- `constants`: numeric symbols available to objective and constraint expressions.
- `component_overrides`: fixed `Mmux`/`Mmuz` slot overrides for ladder-style clamps.
- `inertia_events`: momentum-threshold helper events. Events are axis-specific
  and use an explicit `retention_multiplier` because hit events also zero the
  stored `Imux`/`Imuz` array entry. `hit` expands into two linear post-retention
  bounds; `avoid` requires `direction` and emits one signed lower bound.
- `objective.expression`: Mathematica expression string.
- `constraints[*].expression`: Mathematica expression strings.
- `optimizer`: optional Wolfram optimizer controls. The canonical optimizer
  currently accepts `accuracy_goal`, `precision_goal`, `working_precision`,
  `max_iterations`, and `method`.

Slots are 1-based to match Mathematica indexing.

## Optimization Request

Produced by the future mod UI or route builder. Consumed by the Python
orchestrator.

Schema: `schemas/optimization_request.schema.json`

Status: v1 input-first request contract.

The request schema now mirrors the staged pipeline rather than the old generic
`keyboard_inputs`/`objectives` shape:

- `initial_state`: starting player state.
- `movement_plan`: semantic movement slots.
- `constraints`: typed exact constraints with per-constraint Mathematica and
  exact tolerances.
- `exact_objective`: objective axis/slot, optional expression override, and
  solution tolerance.
- `solver`: staged-solve and exact-repair settings.

## Movement Plan

Produced by a user-authored file, future mod UI, or route builder. Consumed by
the Python orchestrator and the Python solver.

Schema: `schemas/movement_plan.schema.json`

Status: v1 source-of-truth movement contract for supported exact-solver cases.

The movement plan records semantic slot inputs instead of derived `Mmu`/`Imu`
numbers:

- `slots[*].kind`: either `init` for an authoritative incoming horizontal
  velocity slot or `movement` for a normal Minecraft movement slot.
- `init` slots provide `speed`, `imux`, and `imuz` directly. The speed is not
  validated against keyboard movement; it is plugged in as the first `Mmu`
  entry, and its direction is carried by the slot's movement-direction angle.
  The exact solver decomposes init speed with `std::sin`/`std::cos`, not
  Minecraft `mcsin`/`mccos`, because init is an external speed vector.
- `slots[*].controls`: fixed keyboard inputs for the slot.
- `slots[*].acceleration.medium`: the movement acceleration context. Current
  exact support covers `ground`, `air`, `water`, and `lava` for forward no-45
  and forward-45 inputs.
- `slots[*].retention.medium`: the post-move retention context. This is
  separate from acceleration so unusual fixed-tick cases can override drag
  provenance without changing the acceleration path.
- `slots[*].wall_hit.axes`: explicit fixed-tick wall-hit annotation. For an X
  wall, the generated/exact model zeros that slot's X retention while preserving
  Z retention; Z walls do the opposite. No position clamp (the optimizer
  re-anchors coordinates).
- `slots[*].wall_collision` `{axis, value}`: threshold collision used by the
  exact solver. After the slot's move, if the axis crosses `value`, the solver
  clamps the position to `value` and zeroes that axis's velocity (real Minecraft
  moveEntity clamping). The command parser produces this from the
  `s[hitx=val]`/`s[hitz=val]` modifier; see docs/current-status.md.
- `slots[*].web` / `slots[*].ladder`: cobweb (¼ motion + prev-web carry zero) and
  ladder (±0.15 clamp) flags.

The orchestrator derives Mathematica `arrays.imux`, `arrays.imuz`, and
`arrays.mmu` directly from this plan. The exact solver independently derives
the same physical values rather than trusting rounded JSON constants.
For `inertia_events`, the orchestrator adds the Mathematica
`retention_multiplier` from the generated arrays. Hit events zero the matching
Mathematica `Imux`/`Imuz` entry; avoid events leave arrays unchanged. The exact
solver evaluates inertia residuals against post-retention velocity before the
normal `0.005` threshold zeroing.

## Mathematica Output

Produced by Mathematica. Consumed by the Python orchestrator.

Status: v1 implemented by `mathematica/optimize.wls`.

Expected role:

- Return approximate movement-direction angles.
- Include enough status/diagnostic information for the orchestrator to decide
  whether to continue to exact solving.
- In the staged flow, typed `position_bounds` constraints are materialized by
  the orchestrator into expression constraints before calling the canonical
  optimizer.

## Exact Solver Input

Produced by the Python orchestrator. Consumed by the Python solver.

Schema: `schemas/exact_solver_input.schema.json`

Status: v1 input-first contract with low-level compatibility.

New exact-solver inputs carry the movement plan and the selected optimizer
result:

- `n`: number of movement-direction slots.
- `angle_domain.table_size`: Minecraft's discrete `2^16` angle table.
- `initial_state`: exact solver starting position and velocity.
- `movement_plan`: semantic movement slots used to derive exact movement.
- `optimal_solution.movement_directions`: Mathematica's chosen movement
  directions, indexed by 1-based slot. The exact solver consumes the radians
  value as the authoritative angle; degrees are retained for diagnostics and
  human inspection.
- `optimal_solution.points`: optional Mathematica model points for diagnostics.
- `derived_model`: optional generated Mathematica arrays, constraints, and
  diagnostics. This is for inspection only; the exact solver derives movement
  from `movement_plan`.
- `constraints`: typed exact constraints. Each constraint can carry its own
  `mathematica_tolerance` for relaxed Wolfram solves and `exact_tolerance` for
  byte-exact validation.
- `exact_objective`: objective axis/slot plus solution tolerance used to keep
  the relaxed Mathematica result and exact repair close to the approximate
  route.

Movement-state timing rules that the contracts must be able to represent:

- Chained incoming momentum can be represented as an `init` contribution before
  the first newly simulated tick.
- Sprint is an ATTRIBUTE carried per slot in `controls.sprint`. Its boost is
  applied immediately on ground and delayed by one tick in air (the previous
  slot's value), matching mothball's `prev_sprint`. The solver does NOT strip
  sprint for sneak/water/lava/wall — water/lava simply take the no-boost
  acceleration branch, and the PLAN BUILDER (command parser or optimizer) sets
  the attribute per tick (e.g. drops it at a wall tick so exactly one no-sprint
  air slot follows). Sneaking removes the sprint keyboard input but not an
  already-true attribute; the one-tick air delay yields the sneaksprint window.
- Water/lava movement still has 45/no-45 input behavior, even though normal
  sustained sprinting does not apply there.
- Momentum threshold is applied independently for X and Z after slipperiness.
  If the end-of-tick component is below the threshold, that component is zeroed;
  v1 models this as a post-retention threshold constraint plus an explicit zero
  in the affected `Imux` or `Imuz` for inertia-hit events.

Exact-solver numeric policy:

- Position and velocity state are stored as double/float64 in the current
  reduced horizontal simulation to match anon-noob mothball `player.py` under
  NumPy 1.26 scalar promotion.
- Movement-plan inputs derive acceleration and retention values through the same
  float32 movement-intermediate operation sequences used by the reference
  implementation before applying them to the double state.
- Movement direction stays in radians internally. The solver flips sign from
  Mathematica movement direction to Minecraft yaw radians.
- `mcsin`/`mccos` use Minecraft's float32 angle indexing formulas with a
  65536-entry domain, but currently compute the indexed sine value using
  `std::sin` on demand instead of storing a table.
- Degree conversion is output-only for `angles_discrete` diagnostics and macro
  relative yaw deltas.

## Block Route Input

Schema: `schemas/block_route_input.schema.json`

Status: high-level authoring contract that compiles to the existing
exact-template shape.

The block route input describes an ordered list of axis-aligned landing blocks
plus optional solid avoid blocks:

- `landing_blocks[0]` is the starting/departure block and defines the relative
  coordinate origin for generated constraints. Legacy `blocks` is still accepted
  as an alias.
- Each following block is a landing target.
- `x`, `y`, `z` are block lower-corner coordinates; the landing surface is
  `y + 1`.
- `width` and `length` default to `1`.
- `run_ticks` defaults to `defaults.run_ticks` or `0` and belongs to the block
  being departed from. It is rejected on the final block.
- `avoid_blocks[*]` are separate solid blocks with `between: [from, to]`
  identifying the consecutive landing-block segment where they apply. `height`
  defaults to `1`; optional `corner_hints` and `transition_tick_window` narrow
  candidate enumeration.
- `candidate_selection` controls avoid candidate generation and scoring:
  `max_generated_candidates`, `max_precise_candidates`, `objective_margin`,
  `coarse_tolerance`, `wolfram_timeout`, and `coarse_optimizer` (`method`,
  `accuracy_goal`, `precision_goal`, `max_iterations`). CLI flags can override
  these values. Coarse Wolfram failures and timeouts remain attached to the
  failed candidate as diagnostics and are excluded from precise candidate
  selection.

For each segment from departure block to target block, the compiler emits:

- `run_ticks` ground sprint movement slots, each with a running
  `position_bounds` constraint on the departure block.
- One ground sprint-jump slot.
- A mothball-vertical-derived number of sprint-45 air slots.
- One landing `position_bounds` constraint on the target block at the segment end
  slot.

For avoid blocks, normal block collision is baked into constraints by
enumerating alternatives. The builder first inflates the avoid rectangle by the
player half-width and uses the mothball vertical trace to find ticks where the
player vertical AABB overlaps the block. It then emits candidate templates with
per-tick side constraints such as `x <= west_edge`, `x >= east_edge`,
`z <= north_edge`, or `z >= south_edge`. One-corner and two-corner schedules
produce ordinary conjunctive `position_bounds` constraints, so the existing
Mathematica and exact-solver contracts do not need native `Or` support.

Candidate bundles can be passed to `score-block-route`, which runs a coarse
Wolfram solve with forced relaxed constraint tolerance and low optimizer goals,
then records `coarse_score`, rank, and selected candidate ids. This scoring pass
is only a pruning/ranking step; final movement directions still come from the
normal strict/relaxed staged solve on the selected exact templates.

Horizontal block overlap constraints use player-center overlap. For a block
spanning `[x, x + width]` and `[z, z + length]`, generated bounds are:

```text
min_x = block.x - 0.3 - origin.x
max_x = block.x + width + 0.3 - origin.x
min_z = block.z - 0.3 - origin.z
max_z = block.z + length + 0.3 - origin.z
```

The compiler does not hand-author `Imux`, `Imuz`, or `Mmu`; the staged solver
continues to derive those arrays from the generated `movement_plan`.

## Macro CSV

Produced by the Python solver.

Schema notes: `schemas/macro_csv.md`

Status: external macro-tool format documented.

The CSV columns are `W,A,S,D,P,N,J,YAW,PITCH,L,R,COUNT,H`. `W/A/S/D` are movement
keys, `P` is sprint, `N` is sneak, `J` is jump, `YAW` and `PITCH` are relative
degree deltas, `L/R` are click fields, `COUNT` is the row repeat count, and `H`
is a reserved field currently emitted as `0`.

The solver writes JSON to stdout and can also write the external CSV with
`--macro-csv-out path/to/macro.csv`.
