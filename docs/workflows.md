# Workflows

## Core Pipeline Priority

Current priority order:

1. Define the Mathematica input contract from the actual Mathematica needs.
2. Define the exact solver input contract from the optimizer model plus the
   selected Mathematica movement directions.
3. Document the existing external macro-tool CSV output format.
4. Harden the staged Python orchestrator flow from an exact-input template to
   strict Mathematica, relaxed Mathematica, and Python solver.
5. Return to Forge mod GUI/in-game quality-of-life features later.

The first two contracts now have v1 low-level schemas:

- `schemas/mathematica_input.schema.json`
- `schemas/exact_solver_input.schema.json`

Do not expand the Forge mod until the core contracts and orchestrator flow are
stable.

## Movement Modeling Notes

The current Mathematica example uses a closed-form contribution model:

- `Mmu`: horizontal acceleration magnitude per slot.
- `Imux`/`Imuz`: horizontal velocity retention per slot.
- `F`: movement direction variables, not Minecraft yaw.

Important timing rules learned so far:

- Chained simulations usually start with an `init` slot from tick 0 to tick 1.
- `controls.sprint` is the sprint ATTRIBUTE (what applies the boost), distinct
  from the sprint keyboard input. The solver applies the boost from it: immediate
  on ground, delayed one tick in air (previous slot's value), matching mothball's
  `prev_sprint`. The solver does NOT strip sprint for sneak/water/lava/wall;
  water/lava no-boost is the acceleration branch, and the plan builder sets the
  attribute per tick.
- Sneaking removes the sprint keyboard input but not an already-true attribute;
  the one-tick air delay lets the attribute persist one air tick after sneaking
  (the sneaksprint tech). Drop `controls.sprint` from the tick the keyboard is
  removed and the delay reproduces it.
- Water/lava support 45/no-45 input factors but not normal sustained sprinting.
- Slime ground drag is `0.728`. For chained `init` -> flat sprint jump -> slime
  bounce -> flat landing, use `n = 22` for the post-bounce landing condition;
  slot 23 is available as the extra chained state.
- Wall hits are approximated by fixing a hit tick, re-anchoring coordinates at
  the wall contact point, and canceling only the blocked axis via `Imux` or
  `Imuz`. For an X wall, set `Imux[[m1]] = 0` and leave `Imuz` unchanged.
- Momentum threshold is applied independently to X/Z components after
  slipperiness. An inertia-hit tick adds two linear per-axis post-retention
  bounds and zeros the matching `Imux`/`Imuz` array entry. An inertia-avoid tick
  specifies `positive` or `negative` direction, adds one signed lower-bound
  constraint, and keeps the array unchanged.
- Player-center wall/landing calculations use half-width `0.3`. A block
  `[b, b+1]` overlaps the player center range `[b - 0.3, b + 1.3]`.
- If sprint is held and the player hits a wall for only one airborne tick, use
  one delayed wall-sprint slot, then one no-sprint air slot, then sprint can
  resume once the player is no longer hitting the wall.
- Ladder interactions distinguish the thin `0.125b` physical hitbox from the
  climbable/restricted movement voxel. The ladder voxel is mostly `1x1x1` in
  coordinates, with the mounted axis restricted to `.0 -> .575` or `.425 -> 1.0`.
  Inside that voxel, shift prevents falling and horizontal speed is capped.
- Ladder horizontal clamps can be approximated by fixed tick/axis overrides: set
  the affected `Mmux`/`Mmuz` component to `+/-0.15` and zero the matching
  `Imux`/`Imuz` entry to cancel prior momentum on that axis.

## Mathematica Example

The user-confirmed local command for the readable example simulation is:

```sh
wolframscript -file examples/mathematica_sim.wls
```

Codex should run `wolframscript` commands unsandboxed for verification. A
sandboxed shell may not see the Wolfram kernel configuration even when the same
command works in the user's terminal.

If a non-interactive shell cannot find the kernel, inspect:

```sh
wolframscript -configure
```

The Wolfram app kernel path on this Mac is:

```sh
/Applications/Wolfram.app/Contents/MacOS/WolframKernel
```

The JSON-driven optimizer entrypoint is:

```sh
wolframscript -file mathematica/optimize.wls examples/simple_jump/mathematica_input.json
```

It reads the v1 Mathematica input schema and prints a single RawJSON object to
stdout. Movement directions are approximate optimizer angles, not Minecraft yaw.

The wall/ladder fixture exercises separated `Imux`/`Imuz` and `Mmux` component
overrides:

```sh
wolframscript -file mathematica/optimize.wls examples/simple_jump/wall_ladder_mathematica_input.json
```

The inertia-threshold fixture exercises generated hit/avoid constraints:

```sh
wolframscript -file mathematica/optimize.wls examples/simple_jump/inertia_mathematica_input.json
```

The Python orchestrator can also render an inspectable Wolfram script from a
Mathematica input schema file:

```sh
PYTHONPATH=orchestrator python3 -m wolframtas_orchestrator render-mathematica \
  examples/involved_mathematica_input.json \
  --out examples/involved_from_schema.wls
```

The orchestrator runs the canonical Mathematica optimizer and writes the
approximate solution JSON with:

```sh
PYTHONPATH=orchestrator python3 -m wolframtas_orchestrator run-mathematica \
  examples/simple_jump/mathematica_input.json \
  --approx-out /tmp/wolframtas_approx_solution.json
```

## Python Orchestrator Fixture

The initial orchestrator supports a fixture-friendly no-op mode:

```sh
python3 -m wolframtas_orchestrator examples/simple_jump/request.json \
  --approx-solution examples/simple_jump/approx_solution.json \
  --exact-solution-out /tmp/wolframtas_exact_solution.json
```

## Staged Exact Flow

For current input-first fixtures, the orchestrator can run the two-pass
Mathematica flow and hand the relaxed solution to the Python solver:

```sh
PYTHONPATH=orchestrator python3 -m wolframtas_orchestrator solve-exact-input \
  examples/simple_jump/repair_exact_solver_input.json \
  --strict-out /tmp/wolframtas_strict.json \
  --relaxed-out /tmp/wolframtas_relaxed.json \
  --exact-input-out /tmp/wolframtas_exact_input.json \
  --exact-out /tmp/wolframtas_exact.json \
  
```

This command derives Mathematica `Imux`/`Imuz`/`Mmu` arrays from
`movement_plan`, materializes typed `position_bounds` constraints into Wolfram
expressions, solves strict constraints first, solves relaxed constraints second,
checks relaxed objective drift against `solution_tolerance`, then invokes the
exact solver with the relaxed movement directions.

## Python Solver

`orchestrator/wolframtas_orchestrator/python_solver.py` drives mothball's
`Player.move()` directly for each movement slot. Usage:

```python
from wolframtas_orchestrator.python_solver import solve, write_macro_csv
solution = solve(exact_input_dict)
write_macro_csv(Path("/tmp/macro.csv"), solution)
```

## Tests

Use the `.venv-oracle` virtualenv for all Python (numpy 1.26 + pytest); plain
`python3` here lacks pytest and has the wrong numpy. See the "Toolchain" section
of `docs/current-status.md` for the one-time setup.

Run unit/component tests without real Wolfram:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=orchestrator .venv-oracle/bin/python -B -m pytest orchestrator/tests
```

Run no-mock end-to-end tests (real `wolframscript` + mothball oracle):

```sh
PYTHONPATH=orchestrator .venv-oracle/bin/python -m pytest e2e
```

## Forge Mod

The mod is scaffolded for Forge 1.8.9 and Java 8. Dependency download is not
checked into the repo.

```sh
./gradlew -v
./gradlew :mod:setupDecompWorkspace
./gradlew :mod:build
./gradlew :mod:runClient
```

On macOS, `./gradlew` auto-selects `/usr/libexec/java_home -v 1.8` when
`JAVA_HOME` is not already set. ForgeGradle 2.x should be run with Java 8, not
with the system default Java 17/21.

Verified on macOS ARM:

- Host architecture: `arm64`.
- Java used by Gradle: Temurin `1.8.0_472`, running as `x86_64`.
- Gradle wrapper: `2.14.1`.
- ForgeGradle resolved as `2.1.3-g6a7c715`.
- `./gradlew --no-daemon :mod:setupDecompWorkspace` succeeds.
- `./gradlew --no-daemon :mod:build` succeeds.

The wrapper sets `-Dorg.gradle.native=false` because Gradle 2.14.1's old native
integration can fail to load `libnative-platform.dylib` on modern macOS ARM
setups.
