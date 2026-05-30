#include "wolframtas/angle_table.hpp"

#include <iostream>
#include <sstream>
#include <string>

namespace {

std::string read_stdin() {
    std::ostringstream buffer;
    buffer << std::cin.rdbuf();
    return buffer.str();
}

} // namespace

int main() {
    const std::string input = read_stdin();
    if (input.empty()) {
        std::cerr << "wolframtas_solver expected approximate solution JSON on stdin\n";
        return 1;
    }

    // Placeholder output until the exact movement solver owns JSON parsing.
    // The angle helpers are compiled here now so the first exact behavior has tests.
    const int yaw_index = wolframtas::degrees_to_index(0.0);
    const int pitch_index = wolframtas::degrees_to_index(0.0);
    const double yaw = wolframtas::index_to_degrees(yaw_index);
    const double pitch = wolframtas::index_to_degrees(pitch_index);

    std::cout
        << "{\n"
        << "  \"version\": 1,\n"
        << "  \"status\": \"solved\",\n"
        << "  \"angles_discrete\": [\n"
        << "    { \"tick\": 0, \"yaw_index\": " << yaw_index
        << ", \"pitch_index\": " << pitch_index
        << ", \"yaw_degrees\": " << yaw
        << ", \"pitch_degrees\": " << pitch << " }\n"
        << "  ],\n"
        << "  \"states_exact\": [],\n"
        << "  \"macro_rows\": [],\n"
        << "  \"diagnostics\": { \"mode\": \"placeholder\" }\n"
        << "}\n";

    return 0;
}
