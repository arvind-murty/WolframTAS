#include "wolframtas/exact_movement.hpp"

#include <cassert>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <vector>

namespace {

wolframtas::MovementSlot init_slot(int slot, double speed) {
    wolframtas::MovementSlot movement_slot;
    movement_slot.slot = slot;
    movement_slot.kind = "init";
    movement_slot.init_speed = speed;
    movement_slot.init_imux = 0.91;
    movement_slot.init_imuz = 0.91;
    return movement_slot;
}

wolframtas::MovementSlot movement_slot(
    int slot,
    const std::string& acceleration_medium,
    const std::string& retention_medium,
    const std::string& acceleration_input,
    int strafe) {
    wolframtas::MovementSlot movement_slot;
    movement_slot.slot = slot;
    movement_slot.kind = "movement";
    movement_slot.controls.forward = 1;
    movement_slot.controls.strafe = strafe;
    movement_slot.controls.jump = slot == 2;
    movement_slot.controls.sprint = true;
    movement_slot.acceleration_medium = acceleration_medium;
    movement_slot.retention_medium = retention_medium;
    movement_slot.acceleration_input = acceleration_input;
    return movement_slot;
}

wolframtas::ExactInput flat_sprint_jump_input(bool air_45) {
    wolframtas::ExactInput input;
    input.n = 12;
    input.movement_slots.push_back(init_slot(1, 0.0));
    input.movement_slots.push_back(movement_slot(2, "ground", "flat_ground", "no45_forward", 0));
    for (int slot = 3; slot <= 12; ++slot) {
        input.movement_slots.push_back(movement_slot(
            slot,
            "air",
            "air",
            air_45 ? "forward_45" : "no45_forward",
            air_45 ? 1 : 0));
    }
    // Movement direction (resultant) is +z (0) for every slot; the solver
    // derives the +45 deg facing for the air-45 slots from forward+strafe.
    input.movement_direction_radians.assign(12, 0.0);
    wolframtas::derive_arrays_from_movement_plan(input);
    wolframtas::validate_exact_input(input);
    return input;
}

// Exact, bit-for-bit equality. These pin deterministic float64 results (the
// locked mothball-matching outputs); there is no acceptable tolerance.
void assert_exact(double actual, double expected) {
    if (actual != expected) {
        std::cerr << std::setprecision(17)
                  << "expected " << expected << ", got " << actual
                  << ", diff " << (actual - expected) << "\n";
        assert(false);
    }
}

} // namespace

// Structural invariants of the C++ solver itself. The movement PHYSICS (the
// actual x/z/vx/vz values) is validated bit-exact against the mothball reference
// simulator in e2e/test_command_parser.py — the source of truth — so nothing
// here hardcodes a self-generated trajectory magnitude. These check properties
// that must hold by construction and compare only to an exact 0.
int main() {
    {
        // A symmetric 45 input (W+A, facing derived as 45 deg) must travel purely
        // along +z and leave EXACTLY zero perpendicular (x) drift. This is the
        // whole reason the solver is built with -ffp-contract=off: a fused
        // strafe*cos - forward*sin would round one product at extended precision
        // and leave a ~1e-9 x drift. Guard it at the unit level; the same x == 0
        // is also confirmed against mothball in the command-parity test.
        wolframtas::ExactInput input = flat_sprint_jump_input(true);
        const std::vector<wolframtas::State> states =
            wolframtas::simulate(input, wolframtas::seed_yaw_indices(input));
        for (const wolframtas::State& state : states) {
            assert_exact(state.x, 0.0);
            assert_exact(state.move_vx, 0.0);
            assert_exact(state.vx, 0.0);
        }
    }
    {
        // An X wall cancels the x axis: derived imux is 0, so the retained x
        // velocity after the tick is exactly 0 while z momentum is untouched.
        wolframtas::ExactInput input;
        input.n = 2;
        input.movement_slots.push_back(movement_slot(1, "water", "water", "no45_forward", 0));
        input.movement_slots.push_back(movement_slot(2, "lava", "lava", "forward_45", 1));
        input.movement_slots.at(0).controls.jump = false;
        input.movement_slots.at(0).wall_hit_x = true;
        input.movement_slots.at(1).controls.jump = false;
        input.movement_direction_radians.assign(2, 0.0);
        wolframtas::derive_arrays_from_movement_plan(input);
        wolframtas::validate_exact_input(input);
        assert_exact(input.imux.at(0), 0.0);
        const std::vector<wolframtas::State> states =
            wolframtas::simulate(input, wolframtas::seed_yaw_indices(input));
        assert_exact(states.at(1).retained_vx, 0.0);
    }
    return 0;
}
