from __future__ import annotations

from wolframtas_orchestrator.movement_model import (
    air_retention,
    air_sprint_45_mmu,
    air_sprint_no45_mmu,
    air_walk_45_mmu,
    air_walk_no45_mmu,
    derive_movement_model,
    derive_movement_arrays,
    flat_ground_retention,
    flat_sprint_jump_no45_mmu,
    flat_walk_no45_mmu,
    fluid_45_mmu,
    fluid_no45_mmu,
    ice_retention,
    lava_retention,
    slime_retention,
    water_retention,
)


def test_known_no45_values_match_reference_paths() -> None:
    assert flat_ground_retention() == 0.546000063419342
    assert air_retention() == 0.9100000262260437
    assert flat_sprint_jump_no45_mmu() == 0.32739998400211334
    assert air_sprint_no45_mmu() == 0.0254799984395504
    assert air_sprint_45_mmu() == 0.025999998673796654
    assert air_walk_no45_mmu() == 0.019600000232458115
    assert air_walk_45_mmu() == 0.019999999552965164
    assert flat_walk_no45_mmu() == 0.09800000488758087
    assert water_retention() == 0.800000011920929
    assert lava_retention() == 0.5000000596046448
    assert slime_retention() == 0.7280000448226929
    assert ice_retention() == 0.891800045967102
    assert fluid_no45_mmu() == 0.019600000232458115
    assert fluid_45_mmu() == 0.019999999552965164


def test_derive_flat_sprintjump_arrays_from_movement_plan() -> None:
    plan = {
        "version": 1,
        "slot_indexing": "1_based",
        "slots": [
            {
                "slot": 1,
                "kind": "init",
                "speed": 0.0,
                "imux": air_retention(),
                "imuz": air_retention(),
            },
            {
                "slot": 2,
                "kind": "movement",
                "controls": {"forward": 1, "strafe": 0, "jump": True, "sneak": False, "sprint": True},
                "acceleration": {"medium": "ground"},
                "retention": {"medium": "flat_ground"},
            },
            {
                "slot": 3,
                "kind": "movement",
                "controls": {"forward": 1, "strafe": 0, "jump": False, "sneak": False, "sprint": True},
                "acceleration": {"medium": "air"},
                "retention": {"medium": "air"},
            },
        ],
    }

    arrays = derive_movement_arrays(plan)

    assert arrays["imux"] == [air_retention(), flat_ground_retention(), air_retention()]
    assert arrays["imuz"] == [air_retention(), flat_ground_retention(), air_retention()]
    assert arrays["mmu"] == [
        0.0,
        flat_sprint_jump_no45_mmu(),
        air_sprint_no45_mmu(),
    ]


def test_derive_init_slot_as_first_mmu_entry() -> None:
    plan = {
        "version": 1,
        "slot_indexing": "1_based",
        "slots": [
            {
                "slot": 1,
                "kind": "init",
                "speed": 0.25,
                "imux": air_retention(),
                "imuz": flat_ground_retention(),
            }
        ],
    }

    model = derive_movement_model(plan)

    assert model["arrays"] == {
        "imux": [air_retention()],
        "imuz": [flat_ground_retention()],
        "mmu": [0.25],
    }


def test_derive_air_sprint_45_from_movement_plan() -> None:
    plan = {
        "version": 1,
        "slot_indexing": "1_based",
        "slots": [
            {
                "slot": 1,
                "kind": "movement",
                "controls": {"forward": 1, "strafe": 1, "jump": False, "sneak": False, "sprint": True},
                "acceleration": {"medium": "air", "input": "forward_45"},
                "retention": {"medium": "air"},
            }
        ],
    }

    arrays = derive_movement_arrays(plan)

    assert arrays["imux"] == [air_retention()]
    assert arrays["imuz"] == [air_retention()]
    assert arrays["mmu"] == [air_sprint_45_mmu()]


def test_derive_fluid_and_wall_hit_from_movement_plan() -> None:
    plan = {
        "version": 1,
        "slot_indexing": "1_based",
        "slots": [
            {
                "slot": 1,
                "kind": "movement",
                "controls": {"forward": 1, "strafe": 0, "jump": False, "sneak": False, "sprint": True},
                "acceleration": {"medium": "water", "input": "no45_forward"},
                "retention": {"medium": "water"},
                "wall_hit": {"axes": ["x"]},
            },
            {
                "slot": 2,
                "kind": "movement",
                "controls": {"forward": 1, "strafe": 1, "jump": False, "sneak": False, "sprint": True},
                "acceleration": {"medium": "lava", "input": "forward_45"},
                "retention": {"medium": "lava"},
            },
        ],
    }

    arrays = derive_movement_arrays(plan)

    assert arrays["imux"] == [0.0, lava_retention()]
    assert arrays["imuz"] == [water_retention(), lava_retention()]
    assert arrays["mmu"] == [fluid_no45_mmu(), fluid_45_mmu()]
