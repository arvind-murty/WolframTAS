#pragma once

#include "wolframtas/solver_types.hpp"

#include <iosfwd>

namespace wolframtas {

void write_solution_json(std::ostream& output, const ExactInput& input, const RepairResult& repair_result);

} // namespace wolframtas
