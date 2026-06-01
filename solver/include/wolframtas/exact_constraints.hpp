#pragma once

#include "wolframtas/solver_types.hpp"

#include <vector>

namespace wolframtas {

Evaluation evaluate_candidate(const ExactInput& input, const std::vector<int>& yaw_indices);
double evaluation_score(const Evaluation& evaluation);

} // namespace wolframtas
