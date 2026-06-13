# Vendored: mothball movement engine

`cogs/movement/*.py` here is vendored verbatim from the mothball project by
anon-noob (https://github.com/anon-noob/mothball), used **with the author's
permission**. Only the movement engine is included (parser + functions + context
+ player). The Discord bot layer (`movement.py`) is intentionally omitted.

WolframTAS uses this as:
- the command-string parser (mothball syntax, e.g. `sj(12)`), and
- the reference movement simulator used directly by the Python exact solver and
  as the bit-exact oracle under numpy 1.26.

Do not edit these files to "fix" behavior — they are the reference. WolframTAS
adapts their output to the `movement_plan` contract in separate, original code.

Runtime deps: `numpy==1.26.x` (NOT 2.x — NEP 50 promotion differs) and
`evalidate`.
