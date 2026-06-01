#include "wolframtas/exact_input.hpp"
#include "wolframtas/exact_movement.hpp"
#include "wolframtas/exact_solver.hpp"
#include "wolframtas/solution_writer.hpp"
#include "wolframtas/solver_types.hpp"

#include <iostream>
#include <sstream>
#include <string>

namespace {

using wolframtas::ExactInput;
using wolframtas::RepairResult;
using wolframtas::derive_arrays_from_movement_plan;
using wolframtas::parse_exact_input;
using wolframtas::repair_angles;
using wolframtas::validate_exact_input;
using wolframtas::write_solution_json;

std::string read_stdin() {
    std::ostringstream buffer;
    buffer << std::cin.rdbuf();
    return buffer.str();
}

} // namespace

int main() {
    const std::string input = read_stdin();
    if (input.empty()) {
        std::cerr << "wolframtas_solver expected exact-solver input JSON on stdin\n";
        return 1;
    }

    try {
        ExactInput exact_input = parse_exact_input(input);
        derive_arrays_from_movement_plan(exact_input);
        validate_exact_input(exact_input);
        const RepairResult repair_result = repair_angles(exact_input);
        write_solution_json(std::cout, exact_input, repair_result);
    } catch (const std::exception& error) {
        std::cerr << "wolframtas_solver failed: " << error.what() << "\n";
        return 1;
    }

    return 0;
}
