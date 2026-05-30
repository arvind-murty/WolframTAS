# Workflows

## Core Pipeline Priority

Current priority order:

1. Define the Mathematica input contract from the actual Mathematica needs.
2. Define the exact solver input contract from the original inputs plus
   Mathematica angles.
3. Document the existing external macro-tool CSV output format.
4. Implement the Python orchestrator so it converts a problem definition into a
   macro CSV by running Mathematica and the C++ exact solver.
5. Return to Forge mod GUI/in-game quality-of-life features later.

Do not expand the Forge mod until the core contracts and orchestrator flow are
stable.

## Movement Modeling Notes

The current Mathematica example uses a closed-form contribution model:

- `Mmu`: horizontal acceleration magnitude per slot.
- `Imux`/`Imuz`: horizontal velocity retention per slot.
- `F`: movement direction variables, not Minecraft yaw.

Important timing rules learned so far:

- Chained simulations usually start with an `init` slot from tick 0 to tick 1.
- Ground sprint state changes are immediate.
- Air sprint activation/removal is delayed by one tick.
- Water, lava, sneaking, and wall hits remove sprint.
- Delayed air sprint is applied only if the receiving tick has no water/lava,
  sneaking, or wall-hit removal condition.
- Water/lava support 45/no-45 input factors but not normal sustained sprinting.
- Slime ground drag is `0.728`. For chained `init` -> flat sprint jump -> slime
  bounce -> flat landing, use `n = 22` for the post-bounce landing condition;
  slot 23 is available as the extra chained state.
- Wall hits are approximated by fixing a hit tick, re-anchoring coordinates at
  the wall contact point, and canceling only the blocked axis via `Imux` or
  `Imuz`. For an X wall, set `Imux[[m1]] = 0` and leave `Imuz` unchanged.
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

## Python Orchestrator Fixture

The initial orchestrator supports a fixture-friendly no-op mode:

```sh
python3 -m wolftas_orchestrator examples/simple_jump/request.json \
  --approx-solution examples/simple_jump/approx_solution.json \
  --exact-solution-out /tmp/wolftas_exact_solution.json
```

## C++ Solver

The solver is scaffolded as a small CLI that reads approximate solution JSON
from stdin and writes exact solution JSON to stdout.

```sh
cmake -S solver -B solver/build
cmake --build solver/build
solver/build/wolftas_solver < examples/simple_jump/approx_solution.json
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
