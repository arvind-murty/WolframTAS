# Macro CSV

The macro CSV is the final player-facing route format produced after exact
solving.

External macro-tool column order:

```csv
W,A,S,D,P,N,J,YAW,PITCH,L,R,COUNT
false,false,false,false,false,false,false,0.0,0.0,0,0,1
```

Column meanings:

- `W`, `A`, `S`, `D`: movement keys as `true` or `false`.
- `P`: sprint key as `true` or `false`.
- `N`: sneak key as `true` or `false`.
- `J`: jump key as `true` or `false`.
- `YAW`: relative yaw delta in degrees, not absolute yaw.
- `PITCH`: relative pitch delta in degrees, not absolute pitch.
- `L`: left-click state/count for the row, currently emitted as `0`.
- `R`: right-click state/count for the row, currently emitted as `0`.
- `COUNT`: number of ticks to repeat this row.

Rows are run-length encoded by `COUNT`. A single uncompressed tick is
represented with `COUNT = 1`.
