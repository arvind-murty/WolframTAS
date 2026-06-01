#include "wolframtas/exact_input.hpp"
#include "wolframtas/exact_movement.hpp"
#include "wolframtas/exact_solver.hpp"
#include "wolframtas/solution_writer.hpp"
#include "wolframtas/solver_types.hpp"

#include <fstream>
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
using wolframtas::write_macro_csv;
using wolframtas::write_solution_json;

std::string read_stdin() {
    std::ostringstream buffer;
    buffer << std::cin.rdbuf();
    return buffer.str();
}

} // namespace

int main(int argc, char** argv) {
    std::string macro_csv_out;
    for (int index = 1; index < argc; ++index) {
        const std::string arg = argv[index];
        if (arg == "--macro-csv-out") {
            if (index + 1 >= argc) {
                std::cerr << "--macro-csv-out requires a path\n";
                return 1;
            }
            macro_csv_out = argv[++index];
            continue;
        }
        std::cerr << "unknown argument: " << arg << "\n";
        return 1;
    }

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
        if (!macro_csv_out.empty()) {
            std::ofstream macro_output(macro_csv_out);
            if (!macro_output) {
                std::cerr << "failed to open macro CSV output: " << macro_csv_out << "\n";
                return 1;
            }
            write_macro_csv(macro_output, exact_input, repair_result);
        }
        write_solution_json(std::cout, exact_input, repair_result);
    } catch (const std::exception& error) {
        std::cerr << "wolframtas_solver failed: " << error.what() << "\n";
        return 1;
    }

    return 0;
}
