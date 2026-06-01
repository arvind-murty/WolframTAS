#include "wolframtas/exact_constraints.hpp"

#include "wolframtas/exact_movement.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>

namespace wolframtas {
namespace {

double state_axis_value(const State& state, const std::string& axis) {
    if (axis == "x") {
        return state.x;
    }
    if (axis == "z") {
        return state.z;
    }
    throw std::runtime_error("unsupported state axis: " + axis);
}

double retained_velocity_axis_value(const State& state, const std::string& axis) {
    if (axis == "x") {
        return state.retained_vx;
    }
    if (axis == "z") {
        return state.retained_vz;
    }
    throw std::runtime_error("unsupported inertia axis: " + axis);
}

void add_bound_residual(Evaluation& evaluation, const std::string& id, double residual) {
    if (residual <= 0.0) {
        return;
    }
    evaluation.residual_norm += residual * residual;
    if (residual > evaluation.worst_constraint_residual) {
        evaluation.worst_constraint_residual = residual;
        evaluation.worst_constraint_id = id;
    }
}

} // namespace

Evaluation evaluate_candidate(const ExactInput& input, const std::vector<int>& yaw_indices) {
    Evaluation evaluation;
    evaluation.states = simulate(input, yaw_indices);
    for (const PositionConstraint& constraint : input.constraints) {
        if (constraint.slot < 0 || constraint.slot >= static_cast<int>(evaluation.states.size())) {
            throw std::runtime_error("constraint slot is outside simulated state range: " + constraint.id);
        }
        const State& state = evaluation.states.at(static_cast<std::size_t>(constraint.slot));
        if (constraint.has_min_x) {
            add_bound_residual(
                evaluation,
                constraint.id,
                constraint.min_x - state.x - constraint.exact_tolerance);
        }
        if (constraint.has_max_x) {
            add_bound_residual(
                evaluation,
                constraint.id,
                state.x - constraint.max_x - constraint.exact_tolerance);
        }
        if (constraint.has_min_z) {
            add_bound_residual(
                evaluation,
                constraint.id,
                constraint.min_z - state.z - constraint.exact_tolerance);
        }
        if (constraint.has_max_z) {
            add_bound_residual(
                evaluation,
                constraint.id,
                state.z - constraint.max_z - constraint.exact_tolerance);
        }
    }

    for (const InertiaEvent& event : input.inertia_events) {
        if (event.slot < 0 || event.slot >= static_cast<int>(evaluation.states.size())) {
            throw std::runtime_error("inertia event slot is outside simulated state range: " + event.id);
        }
        const double velocity = retained_velocity_axis_value(
            evaluation.states.at(static_cast<std::size_t>(event.slot)),
            event.axis);
        if (event.type == "hit") {
            add_bound_residual(evaluation, event.id, std::abs(velocity) - event.threshold);
        } else if (event.direction == "positive") {
            add_bound_residual(evaluation, event.id, event.threshold - velocity);
        } else if (event.direction == "negative") {
            add_bound_residual(evaluation, event.id, event.threshold + velocity);
        } else {
            throw std::runtime_error("unsupported inertia event: " + event.id);
        }
    }
    evaluation.residual_norm = std::sqrt(evaluation.residual_norm);

    if (input.objective.enabled) {
        if (input.objective.slot < 0 || input.objective.slot >= static_cast<int>(evaluation.states.size())) {
            throw std::runtime_error("exact_objective.slot is outside simulated state range");
        }
        evaluation.objective_value = state_axis_value(
            evaluation.states.at(static_cast<std::size_t>(input.objective.slot)),
            input.objective.axis);
        evaluation.objective_deviation = std::abs(evaluation.objective_value - input.objective.target_value);
        evaluation.objective_residual = std::max(0.0, evaluation.objective_deviation - input.objective.tolerance);
    }
    evaluation.feasible = evaluation.residual_norm == 0.0 && evaluation.objective_residual == 0.0;
    return evaluation;
}

double evaluation_score(const Evaluation& evaluation) {
    return evaluation.residual_norm + evaluation.objective_residual;
}

} // namespace wolframtas
