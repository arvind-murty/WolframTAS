"""Parse mothball command strings, run the WolframTAS C++ solver on each derived
exact-solver input, and assert the result matches the vendored mothball
simulator. Run under the numpy-1.26 venv (it imports the vendored engine):

    PYTHONPATH=orchestrator .venv-oracle/bin/python e2e/check_command_sim.py

With no args it checks DEFAULT_COMMANDS; otherwise it checks the given commands.
Exits 0 only if every command matches bit-exact. Used by test_command_parser.py.

To add a test case, just add a mothball command string to DEFAULT_COMMANDS — the
expected result is mothball's own simulation, so no hand-computed values needed.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "orchestrator"))
from wolframtas_orchestrator.command_parser import parse_command  # noqa: E402

SOLVER = REPO / "solver/build/wolframtas_solver"

DEFAULT_COMMANDS = [
    # ground walk / sprint / jumps
    "walk(10)", "sprint(8)", "wj(5)", "sprintjump(6)", "sneakjump(4)",
    # sprint-jump
    "sj(12)", "sj(20)",
    # 45 strafe (ground) — exercises perpendicular-drift cancellation vs mothball
    "s45(8)", "w45(6)", "sj45(10)", "sj45(12)",
    # sneak / sneaksprint
    "sn(5)", "sns(6)", "sns45(7)",
    # air
    "walkair(5)", "sprintair(5)", "sneaksprintair(5)",
    # water / lava
    "walkair(5, water=true)", "sprintair(6, water=true)",
    "walkair(5, lava=true)", "sprintair(5, lava=true)",
    # slime / ice (setslip changes ground slipperiness)
    "setslip(0.8) walk(4)", "setslip(0.8) sj(8)", "setslip(0.98) walk(5)",
    # ladder (incl. the >0.15 clamp engaging after a sprint-jump) / web (incl.
    # the prev-web velocity zeroing on the tick after leaving a web)
    "walkair(5, ld=true)", "sprintjump(1) walkair(4, ld=true)",
    "walkair(5, web=true)", "sprintair(1, web=true) sprintair(3)",
    # sneak variants
    "sn45(5)",
    # explicit facing (rotation arg), including non-clean angles and 45
    "sprint(8, 45)", "walk(10, 30)", "sj45(10, 12.7)", "w45(6, 90)", "sns45(7, 22.5)",
    # multi-command sequences
    "sj s45(11)", "wj(5) walk(5)", "sprint(3) walk(3) sprint(3)",
]


def check_one(command: str) -> str | None:
    """Return None on a bit-exact match, else an error message."""
    parsed = parse_command(command)
    exact_input = parsed["exact_input"]
    mothball = parsed["mothball_final"]
    n = exact_input["n"]
    completed = subprocess.run(
        [str(SOLVER)], input=json.dumps(exact_input), text=True, capture_output=True
    )
    if completed.returncode != 0:
        return f"solver failed: {completed.stderr.strip()}"
    states = json.loads(completed.stdout)["states_exact"]
    # mothball reports position one tick before the final velocity; with the
    # leading init slot, position aligns at states[n-1] and velocity at states[n].
    # Compare BOTH axes (z = travel, x = perpendicular drift) and both velocity
    # components, all bit-exact against mothball — no hardcoded expected values.
    checks = (
        ("position x", float(states[n - 1]["position"]["x"]), mothball["x"]),
        ("position z", float(states[n - 1]["position"]["z"]), mothball["z"]),
        ("velocity vx", float(states[n]["velocity"]["x"]), mothball["vx"]),
        ("velocity vz", float(states[n]["velocity"]["z"]), mothball["vz"]),
    )
    for label, solver_value, mothball_value in checks:
        if solver_value != mothball_value:
            return f"{label}: solver {solver_value!r} vs mothball {mothball_value!r}"
    return None


def main() -> int:
    commands = sys.argv[1:] or DEFAULT_COMMANDS
    failures = 0
    for command in commands:
        error = check_one(command)
        if error is None:
            print(f"OK   {command}")
        else:
            print(f"FAIL {command}: {error}")
            failures += 1
    print(f"\n{len(commands) - failures}/{len(commands)} commands matched mothball")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
