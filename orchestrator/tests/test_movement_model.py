from __future__ import annotations

from wolframtas_orchestrator.movement_model import (
    _table,
    derive_movement_arrays,
    derive_movement_model,
    retention_for,
)

# These tests exercise the ARRAY-ASSEMBLY LOGIC only (init passthrough, the
# ground sprint-jump composition, the one-tick air sprint delay, the cobweb
# imu/mmu edits, wall-axis cancellation, fluid input factors). Every expected
# number is sourced from the shared movement_constants table, never hardcoded:
# the constant VALUES are validated as the source of truth elsewhere — bit-exact
# against the mothball simulator in e2e/test_command_parser.py, and against the
# compiled solver + generator in e2e/test_movement_model_consistency.py.

TABLE = _table()
NO45 = TABLE["input_factor"]["no45"]
FORWARD_45 = TABLE["input_factor"]["forward_45"]
BOOST = TABLE["sprintjump_boost"]


def _base(key: str) -> float:
    return TABLE["base_movement"][key]


def _movement_slot(**controls):
    base = {"forward": 1, "strafe": 0, "jump": False, "sneak": False, "sprint": False}
    base.update(controls)
    return base


def test_derive_flat_sprintjump_arrays_from_movement_plan() -> None:
    plan = {
        "version": 1,
        "slot_indexing": "1_based",
        "slots": [
            {"slot": 1, "kind": "init", "speed": 0.0, "imux": retention_for("air"), "imuz": retention_for("air")},
            {
                "slot": 2,
                "kind": "movement",
                "controls": _movement_slot(jump=True, sprint=True),
                "acceleration": {"medium": "ground"},
                "retention": {"medium": "flat_ground"},
            },
            {
                "slot": 3,
                "kind": "movement",
                "controls": _movement_slot(sprint=True),
                "acceleration": {"medium": "air"},
                "retention": {"medium": "air"},
            },
        ],
    }

    arrays = derive_movement_arrays(plan)

    assert arrays["imux"] == [retention_for("air"), retention_for("flat_ground"), retention_for("air")]
    assert arrays["imuz"] == arrays["imux"]
    # Ground sprint-jump: base * no45 factor + sprint-jump boost. Air slot: sprint
    # is delayed one tick, so the prior (sprint-jump) tick's sprint applies here.
    assert arrays["mmu"] == [
        0.0,
        _base("ground_flat_ground_sprint") * NO45 + BOOST,
        _base("air_sprint") * NO45,
    ]


def test_air_sprint_is_delayed_one_tick() -> None:
    plan = {
        "version": 1,
        "slot_indexing": "1_based",
        "slots": [
            # First air slot sprinting, but no prior sprint -> air_walk base.
            {
                "slot": 1,
                "kind": "movement",
                "controls": _movement_slot(sprint=True),
                "acceleration": {"medium": "air"},
                "retention": {"medium": "air"},
            },
            # Now the prior tick was sprinting -> air_sprint base.
            {
                "slot": 2,
                "kind": "movement",
                "controls": _movement_slot(sprint=True),
                "acceleration": {"medium": "air"},
                "retention": {"medium": "air"},
            },
        ],
    }

    arrays = derive_movement_arrays(plan)

    assert arrays["mmu"] == [_base("air_walk") * NO45, _base("air_sprint") * NO45]


def test_web_approximation_edits_imu_and_mmu() -> None:
    factor = TABLE["web_motion_factor"]
    air = retention_for("air")
    plan = {
        "version": 1,
        "slot_indexing": "1_based",
        "slots": [
            # Normal air tick feeding the web tick: its retention is cut by the
            # factor (it scales the momentum carried into the web).
            {
                "slot": 1,
                "kind": "movement",
                "controls": _movement_slot(),
                "acceleration": {"medium": "air"},
                "retention": {"medium": "air"},
            },
            # Web tick: mmu cut by the factor, retention zeroed (carry dropped).
            {
                "slot": 2,
                "kind": "movement",
                "controls": _movement_slot(),
                "acceleration": {"medium": "air"},
                "retention": {"medium": "air"},
                "web": True,
            },
        ],
    }

    arrays = derive_movement_arrays(plan)

    base_air_walk = _base("air_walk") * NO45
    assert arrays["imux"] == [air * factor, 0.0]
    assert arrays["imuz"] == [air * factor, 0.0]
    assert arrays["mmu"] == [base_air_walk, base_air_walk * factor]


def test_derive_init_slot_as_first_mmu_entry() -> None:
    plan = {
        "version": 1,
        "slot_indexing": "1_based",
        "slots": [
            {"slot": 1, "kind": "init", "speed": 0.25, "imux": retention_for("air"), "imuz": retention_for("flat_ground")}
        ],
    }

    model = derive_movement_model(plan)

    # init passes its own speed/retention straight through.
    assert model["arrays"] == {
        "imux": [retention_for("air")],
        "imuz": [retention_for("flat_ground")],
        "mmu": [0.25],
    }


def test_derive_fluid_and_wall_hit_from_movement_plan() -> None:
    plan = {
        "version": 1,
        "slot_indexing": "1_based",
        "slots": [
            {
                "slot": 1,
                "kind": "movement",
                "controls": _movement_slot(sprint=True),
                "acceleration": {"medium": "water", "input": "no45_forward"},
                "retention": {"medium": "water"},
                "wall_hit": {"axes": ["x"]},
            },
            {
                "slot": 2,
                "kind": "movement",
                "controls": _movement_slot(strafe=1, sprint=True),
                "acceleration": {"medium": "lava", "input": "forward_45"},
                "retention": {"medium": "lava"},
            },
        ],
    }

    arrays = derive_movement_arrays(plan)

    # wall_hit on x zeroes only that axis; z keeps the medium retention.
    assert arrays["imux"] == [0.0, retention_for("lava")]
    assert arrays["imuz"] == [retention_for("water"), retention_for("lava")]
    assert arrays["mmu"] == [_base("water") * NO45, _base("lava") * FORWARD_45]
