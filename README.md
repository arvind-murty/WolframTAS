# WolfTAS

WolfTAS is a Forge 1.8.9 Minecraft mod for building and running all-in-one
parkour optimizations.

The intended pipeline is:

1. The Minecraft client mod lets the player describe constraints, objective
   functions, and fixed keyboard inputs for a route.
2. The mod writes a versioned optimization request.
3. The Python orchestrator starts the Wolfram/Mathematica optimizer.
4. Mathematica emits an approximate solution.
5. The orchestrator passes that solution to the C++ exact solver.
6. The exact solver snaps/validates the route against Minecraft movement,
   floating point behavior, and the `2^14` discrete angle table.
7. The mod writes a macro CSV and can render the solved path in-game.

## Repo Layout

- `mod/`: Forge 1.8.9 client mod.
- `orchestrator/`: Python process orchestration between Minecraft,
  Mathematica, and the exact solver.
- `mathematica/`: Wolfram scripts and examples.
- `solver/`: C++ exact movement solver.
- `schemas/`: Versioned JSON contracts shared across components.
- `examples/`: Small end-to-end fixtures.
- `docs/`: Architecture, workflows, and project decisions.

## Current Status

This repository is in the scaffold stage. The contracts and component entry
points are intentionally small so each layer can be tested independently before
the full Minecraft/Mathematica/C++ integration is wired together.
