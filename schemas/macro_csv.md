# Macro CSV

The macro CSV is the final player-facing route format produced after exact
solving.

Initial column order:

```csv
tick,yaw,pitch,forward,strafe,jump,sneak,sprint
```

Column meanings:

- `tick`: zero-based client tick.
- `yaw`: exact playable yaw in degrees.
- `pitch`: exact playable pitch in degrees.
- `forward`: `-1`, `0`, or `1`.
- `strafe`: `-1`, `0`, or `1`.
- `jump`: `true` or `false`.
- `sneak`: `true` or `false`.
- `sprint`: `true` or `false`.
