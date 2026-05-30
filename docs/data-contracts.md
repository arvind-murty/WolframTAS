# Data Contracts

This file tracks contract boundaries, not final field definitions. The exact
schemas should be filled in only after the Mathematica requirements, exact
solver requirements, and existing macro CSV format are known.

## Mathematica Input

Produced by a user-authored file or future mod UI. Consumed by the Python
orchestrator and Mathematica.

Status: not finalized.

Expected role:

- Describe fixed keyboard inputs.
- Describe constraints.
- Describe objective functions.
- Include any initial Minecraft movement state Mathematica needs.
- Avoid fields that only matter to the Forge GUI.

## Mathematica Output

Produced by Mathematica. Consumed by the Python orchestrator.

Status: partially known.

Expected role:

- Return approximate yaw/pitch angles.
- Include enough status/diagnostic information for the orchestrator to decide
  whether to continue to exact solving.

## Exact Solver Input

Produced by the Python orchestrator. Consumed by the C++ exact solver.

Status: not finalized.

Expected role:

- Include original fixed keyboard inputs.
- Include Mathematica approximate angles.
- Include enough initial state and solver settings for exact Minecraft movement.

Movement-state timing rules that the contracts must be able to represent:

- Chained incoming momentum can be represented as an `init` contribution before
  the first newly simulated tick.
- Sprint activation/removal is immediate on ground and delayed by one tick in
  air.
- Water, lava, sneaking, and wall hits remove sprint.
- Delayed air sprint applies only if the receiving tick is not water, lava,
  sneaking, or a wall-hit tick.
- Water/lava movement still has 45/no-45 input behavior, even though normal
  sustained sprinting does not apply there.

## Macro CSV

Produced by the C++ exact solver.

Status: not finalized.

Use the existing external macro-tool CSV format first. A WolfTAS-native macro
format can be added later if needed.
