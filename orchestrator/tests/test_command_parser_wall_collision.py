from __future__ import annotations

from wolframtas_orchestrator.command_parser import parse_command


def _mothball_final(command: str) -> dict[str, float]:
    # parse_command drives the vendored mothball engine and exposes its final
    # simulator state as mothball_final.
    return parse_command(command)["mothball_final"]


def test_wall_hitz_crossing_unsprints_next_ground_tick_reference() -> None:
    # Desired wall-reference semantics for debugging and parity:
    #   foo[hitz=val](1, rot) bar(2, rot)
    # becomes (if crossing happens on foo's tick):
    #   foo(1, rot) setposz(val) setvz(0) bar(1, rot, sprint=false) bar(1, rot)
    command = "s[hitz=0.05](1,30) s(2,30)"
    expected_reference = "s(1,30) setposz(0.05) setvz(0) s(1,30,sprint=false) s(1,30)"

    parsed = parse_command(command)
    expected = _mothball_final(expected_reference)

    assert parsed["mothball_final"] == expected


def test_wall_hitz_crossing_unsprints_next_air_tick_reference() -> None:
    # Air variant of the same wall-unsprint behavior:
    #   sprintair[hitz=val](1, rot) sprintair(2, rot)
    # becomes (if crossing happens on the hit tick):
    #   sprintair(1, rot) setposz(val) setvz(0)
    #   sprintair(1, rot, sprint=false) sprintair(1, rot)
    command = "sa[hitz=0.01](1,30) sa(2,30)"
    expected_reference = "sa(1,30) setposz(0.01) setvz(0) sa(1,30,sprint=false) sa(1,30)"

    parsed = parse_command(command)
    expected = _mothball_final(expected_reference)

    assert parsed["mothball_final"] == expected


def test_wall_hitz_no_crossing_keeps_normal_reference_path() -> None:
    command = "s[hitz=5.0](1,30) s(2,30)"
    expected_reference = "s(1,30) s(2,30)"

    parsed = parse_command(command)
    expected = _mothball_final(expected_reference)

    assert parsed["mothball_final"] == expected
