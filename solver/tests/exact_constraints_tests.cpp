#include "wolframtas/exact_constraints.hpp"
#include "wolframtas/exact_movement.hpp"

#include <cassert>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <vector>

namespace {

wolframtas::ExactInput stationary_input() {
    wolframtas::ExactInput input;
    input.n = 1;
    wolframtas::MovementSlot slot;
    slot.slot = 1;
    slot.kind = "init";
    slot.init_speed = 0.0;
    slot.init_imux = 0.91;
    slot.init_imuz = 0.91;
    input.movement_slots.push_back(slot);
    input.movement_direction_radians.push_back(0.0);
    wolframtas::derive_arrays_from_movement_plan(input);
    wolframtas::validate_exact_input(input);
    return input;
}

// Exact, bit-for-bit equality. There is no acceptable tolerance.
void assert_exact(double actual, double expected) {
    if (actual != expected) {
        std::cerr << std::setprecision(17)
                  << "expected " << expected << ", got " << actual
                  << ", diff " << (actual - expected) << "\n";
        assert(false);
    }
}

} // namespace

int main() {
    {
        wolframtas::ExactInput input = stationary_input();
        wolframtas::PositionConstraint constraint;
        constraint.id = "inside";
        constraint.slot = 0;
        constraint.has_min_z = true;
        constraint.has_max_z = true;
        constraint.min_z = -1.0;
        constraint.max_z = 1.0;
        constraint.exact_tolerance = 0.0;
        input.constraints.push_back(constraint);

        const wolframtas::Evaluation evaluation = wolframtas::evaluate_candidate(input, wolframtas::seed_yaw_indices(input));
        assert(evaluation.feasible);
        assert_exact(evaluation.residual_norm, 0.0);
    }
    {
        wolframtas::ExactInput input = stationary_input();
        wolframtas::PositionConstraint constraint;
        constraint.id = "lower";
        constraint.slot = 0;
        constraint.has_min_z = true;
        constraint.min_z = 0.2;
        constraint.exact_tolerance = 0.05;
        input.constraints.push_back(constraint);

        const wolframtas::Evaluation evaluation = wolframtas::evaluate_candidate(input, wolframtas::seed_yaw_indices(input));
        // Behavioural: z=0 violates z>=0.2, and this is the worst constraint.
        assert(!evaluation.feasible);
        assert(evaluation.worst_constraint_id == "lower");
    }
    {
        wolframtas::ExactInput input = stationary_input();
        input.objective.enabled = true;
        input.objective.axis = "z";
        input.objective.slot = 0;
        input.objective.target_value = 0.2;
        input.objective.tolerance = 0.05;

        const wolframtas::Evaluation evaluation = wolframtas::evaluate_candidate(input, wolframtas::seed_yaw_indices(input));
        // Behavioural: objective target 0.2 with z=0 exceeds tolerance.
        assert(!evaluation.feasible);
    }
    {
        wolframtas::ExactInput input;
        input.n = 1;
        wolframtas::MovementSlot slot;
        slot.slot = 1;
        slot.kind = "init";
        slot.init_speed = 0.01;
        slot.init_imux = 0.91;
        slot.init_imuz = 0.91;
        input.movement_slots.push_back(slot);
        input.movement_direction_radians.push_back(0.0);
        input.inertia_events.push_back(wolframtas::InertiaEvent{"hit_z", "hit", "z", "", 1, 0.005});
        wolframtas::derive_arrays_from_movement_plan(input);
        wolframtas::validate_exact_input(input);

        const wolframtas::Evaluation evaluation = wolframtas::evaluate_candidate(input, wolframtas::seed_yaw_indices(input));
        // Behavioural: post-retention z velocity exceeds the 0.005 threshold,
        // so the inertia-hit event (requires below threshold) is violated.
        assert(!evaluation.feasible);
        assert(evaluation.worst_constraint_id == "hit_z");
    }
    {
        wolframtas::ExactInput input;
        input.n = 1;
        wolframtas::MovementSlot slot;
        slot.slot = 1;
        slot.kind = "init";
        slot.init_speed = 0.01;
        slot.init_imux = 0.91;
        slot.init_imuz = 0.91;
        input.movement_slots.push_back(slot);
        input.movement_direction_radians.push_back(0.0);
        input.inertia_events.push_back(wolframtas::InertiaEvent{"avoid_z", "avoid", "z", "positive", 1, 0.005});
        wolframtas::derive_arrays_from_movement_plan(input);
        wolframtas::validate_exact_input(input);

        const wolframtas::Evaluation evaluation = wolframtas::evaluate_candidate(input, wolframtas::seed_yaw_indices(input));
        assert(evaluation.feasible);
        assert_exact(evaluation.residual_norm, 0.0);
    }
    return 0;
}
