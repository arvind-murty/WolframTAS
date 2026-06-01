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
    input.movement_direction_radians.assign(12, 0.0);
    wolframtas::derive_arrays_from_movement_plan(input);
    wolframtas::validate_exact_input(input);
    return input;
}

void assert_close(double actual, double expected) {
    if (std::abs(actual - expected) > 1e-15) {
        std::cerr << std::setprecision(17)
                  << "expected " << expected << ", got " << actual
                  << ", diff " << std::abs(actual - expected) << "\n";
        assert(false);
    }
}

} // namespace

int main() {
    {
        wolframtas::ExactInput input = flat_sprint_jump_input(false);
        const std::vector<int> yaw_indices = wolframtas::seed_yaw_indices(input);
        const std::vector<wolframtas::State> states = wolframtas::simulate(input, yaw_indices);
        assert_close(states.at(12).z, 2.6234314852435587);
        assert_close(states.at(12).move_vz, 0.24936001647089573);
    }
    {
        wolframtas::ExactInput input = flat_sprint_jump_input(true);
        const std::vector<int> yaw_indices = wolframtas::seed_yaw_indices(input);
        const std::vector<wolframtas::State> states = wolframtas::simulate(input, yaw_indices);
        assert_close(states.at(12).z, 2.645539114938402);
        assert_close(states.at(12).move_vz, 0.2528878364238645);
    }
    {
        wolframtas::ExactInput input;
        input.n = 1;
        input.movement_slots.push_back(init_slot(1, 0.1));
        input.movement_direction_radians.push_back(0.0);
        wolframtas::derive_arrays_from_movement_plan(input);
        wolframtas::validate_exact_input(input);
        const std::vector<wolframtas::State> states = wolframtas::simulate(input, wolframtas::seed_yaw_indices(input));
        assert_close(states.at(1).z, 0.1);
        assert_close(states.at(1).move_vz, 0.1);
        assert_close(states.at(1).vz, 0.091);
    }
    return 0;
}
