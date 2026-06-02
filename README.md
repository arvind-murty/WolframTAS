# WolframTAS

WolframTAS is a Forge 1.8.9 Minecraft mod for building and running all-in-one
parkour optimizations.

The intended pipeline is:

1. The Minecraft client mod lets the player describe constraints, objective
   functions, and fixed keyboard inputs for a route.
2. The mod writes a versioned optimization request.
3. The Python orchestrator starts the Wolfram/Mathematica optimizer.
4. Mathematica emits an approximate solution.
5. The orchestrator passes that solution to the C++ exact solver.
6. The exact solver snaps/validates the route against Minecraft movement,
   floating point behavior, and the `2^16` discrete angle table.
7. The mod writes a macro CSV and can render the solved path in-game.

## Repo Layout

- `mod/`: Forge 1.8.9 client mod (later quality-of-life layer; not the priority).
- `orchestrator/`: Python process orchestration between Minecraft, Mathematica,
  and the exact solver. Also hosts the mothball command parser and the vendored
  mothball engine (`orchestrator/vendor/`).
- `mathematica/`: Wolfram scripts and examples (`optimize.wls` is canonical).
- `solver/`: C++ exact movement solver.
- `tools/`: `gen_movement_constants.py` — generates the shared imu/mmu constants
  table consumed by both the orchestrator and the solver.
- `schemas/`: Versioned JSON contracts shared across components.
- `examples/`: Small end-to-end fixtures.
- `docs/`: Architecture, workflows, decisions, current status, and next tasks.

## Current Status

The core pipeline works end-to-end: a mothball command (e.g. `sj45(12)`) or a
movement plan flows through the Wolfram optimizer and the C++ exact solver to an
exact solution and a macro CSV. The exact solver is validated **bit-exact against
the mothball reference simulator** across ~46 commands; movement constants have a
single generated source of truth. The Forge mod is still scaffolding.

## Start Here (new contributors and agents)

- **Decisions / stable rules:** `AGENTS.md` (the source of truth; Codex reads
  this, and `CLAUDE.md` imports it for Claude).
- **Handoff snapshot, toolchain setup, and how to run everything:**
  `docs/current-status.md` — read the "Toolchain" section first; tests run under
  a dedicated `.venv-oracle` (numpy 1.26 + pytest) because the vendored mothball
  oracle requires it.
- **What to work on next:** `docs/next-tasks.md`.
- **Contracts:** `docs/data-contracts.md` + `schemas/`.
