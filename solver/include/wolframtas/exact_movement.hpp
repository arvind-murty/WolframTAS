#pragma once

#include "wolframtas/solver_types.hpp"

#include <vector>

namespace wolframtas {

void derive_arrays_from_movement_plan(ExactInput& input);
void validate_exact_input(const ExactInput& input);
std::vector<int> seed_yaw_indices(const ExactInput& input);
std::vector<State> simulate(const ExactInput& input, const std::vector<int>& yaw_indices);

} // namespace wolframtas
