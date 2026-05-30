# Architecture

WolfTAS is centered on a three-step core pipeline. The Forge mod is a later
client around that pipeline, not the source of truth for the initial design.

## Core Pipeline

```text
problem definition
  -> Python orchestrator
  -> Mathematica approximate angles
  -> Python orchestrator
  -> C++ exact solver
  -> macro CSV
```

The first priority is defining the contract for the problem definition consumed
by Mathematica. The second priority is defining the contract for the exact
solver input, which combines original inputs with Mathematica angles. The exact
solver output should initially be the existing external macro-tool CSV format.

## Python Orchestrator

The orchestrator owns process execution and data handoff. Its core job is to
take a problem definition and produce a macro CSV by running Mathematica and the
C++ exact solver in sequence.

## Mathematica Optimizer

The Wolfram scripts solve the approximate continuous optimization problem and
emit angles. The exact required input shape is intentionally not defined yet; it
should be filled in from Mathematica's actual needs.

## C++ Exact Solver

The C++ solver consumes the original inputs plus Mathematica angles, converts
the route into Minecraft-exact movement, and writes the macro CSV. It must
preserve relevant floating point behavior and use Minecraft's discrete angle
domain of `2^14` values.

## Minecraft Mod

The Forge 1.8.9 client mod owns the player-facing workflow:

- GUI for constraints, objectives, fixed keyboard inputs, and solver settings.
- Serialization of world/player state into an optimization request.
- Launching the Python orchestrator.
- Reading or importing macro CSV output.
- Optional render overlay for the solved path.
