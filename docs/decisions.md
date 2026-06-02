# Decisions

## 0001: Use Forge 1.8.9

WolframTAS targets Minecraft Forge 1.8.9.

Implications:

- Java source should stay compatible with Java 8.
- The mod uses the legacy ForgeGradle 2.x toolchain.
- Gradle should be run through the checked-in Gradle 2.14.1 wrapper.
- On macOS ARM, Java 8 may be x86_64 and run through Rosetta; that is expected
  for this legacy toolchain.
- Disable Gradle native integration with `-Dorg.gradle.native=false` for modern
  macOS ARM compatibility.
- Modern Minecraft APIs and mappings should not be assumed.

## 0002: Use JSON Contracts Between Components

The mod, Python orchestrator, Mathematica scripts, and C++ solver exchange
versioned JSON payloads.

Rationale:

- Codex and humans can inspect fixtures cheaply.
- Component tests can run independently.
- Contract changes are explicit.

## 0003: mothball is the source of truth; exact match, no tolerance, no hardcoded numbers

The C++ exact solver must reproduce the vendored mothball reference simulator
(`orchestrator/vendor/`, numpy 1.26) EXACTLY — the same floating-point bits.

- Movement physics is validated only by parsing mothball command strings and
  comparing the solver to mothball bit-exact on x/z/vx/vz
  (`e2e/test_command_parser.py` / `e2e/check_command_sim.py`). No tolerance,
  no epsilon, no `pytest.approx`/`isclose`/`round`.
- Do NOT put hardcoded expected movement numbers in tests — they are
  self-referential and prove nothing. Compare against mothball's own output.
- The solver ctest fixtures may only assert solver behaviour mothball cannot
  express (status, which constraint failed, repaired angle indices, a residual of
  exactly 0, or an axis a wall/threshold zeroes to exactly 0) — never a physics
  magnitude.
- The ONE place a tolerance legitimately lives is the Wolfram CONTINUOUS
  optimizer stage; the exact solver then snaps to the discrete 2^16 angle and the
  exact result is what must match mothball.

This is because the project is tick-perfect: an off-by-1-ULP position is a wrong
answer, and the solver compiles with `-ffp-contract=off` to keep float32
arithmetic bit-identical to numpy (no fused multiply-add).

## 0004: Movement constants have a single source of truth (generated table)

The imu (retention) and mmu (base movement) constants are computed in exactly one
place — `tools/gen_movement_constants.py` (numpy float32) — and emitted as two
committed artifacts both consumers read:

- `orchestrator/wolframtas_orchestrator/movement_constants.json` (orchestrator/Wolfram)
- `solver/include/wolframtas/movement_constants_generated.hpp` (C++ solver, constexpr)

Do not re-derive these constants inline in either component. After changing a
constant, regenerate (needs numpy 1.26) and rebuild the solver.
`e2e/test_movement_model_consistency.py` guards that the committed artifacts
match a fresh generator run and that the JSON matches the compiled solver.
