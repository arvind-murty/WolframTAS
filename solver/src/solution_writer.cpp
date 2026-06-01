#include "wolframtas/solution_writer.hpp"

#include "wolframtas/angle_table.hpp"
#include "wolframtas/exact_movement.hpp"

#include <charconv>
#include <cmath>
#include <cstddef>
#include <iomanip>
#include <ostream>
#include <sstream>
#include <string>
#include <vector>

namespace wolframtas {
namespace {

double wrap_degrees(double degrees) {
    double wrapped = std::fmod(degrees + 180.0, 360.0);
    if (wrapped < 0.0) {
        wrapped += 360.0;
    }
    return wrapped - 180.0;
}

std::string number_string(double value) {
    char buffer[64];
    const auto result = std::to_chars(buffer, buffer + sizeof(buffer), value);
    if (result.ec == std::errc{}) {
        return std::string(buffer, result.ptr);
    }
    std::ostringstream output;
    output << std::setprecision(17) << value;
    return output.str();
}

std::string json_number(double value) {
    if (value == 0.0) {
        return "0";
    }
    if (std::isfinite(value)) {
        return number_string(value);
    }
    return "null";
}

Controls macro_controls_for_slot(const ExactInput& input, int index) {
    if (!input.movement_slots.empty()) {
        return input.movement_slots.at(static_cast<std::size_t>(index)).controls;
    }
    Controls controls;
    controls.forward = 1;
    return controls;
}

struct MacroRow {
    Controls controls;
    double yaw = 0.0;
    double pitch = 0.0;
    int left_click = 0;
    int right_click = 0;
    int count = 1;
};

std::vector<MacroRow> build_macro_rows(const ExactInput& input, const std::vector<int>& yaw_indices) {
    std::vector<MacroRow> rows;
    rows.reserve(static_cast<std::size_t>(input.n));
    for (int index = 0; index < input.n; ++index) {
        const double current_yaw_degrees = index_to_degrees(yaw_indices.at(static_cast<std::size_t>(index)));
        const double previous_yaw_degrees = index == 0
            ? 0.0
            : index_to_degrees(yaw_indices.at(static_cast<std::size_t>(index - 1)));
        rows.push_back(MacroRow{
            macro_controls_for_slot(input, index),
            wrap_degrees(current_yaw_degrees - previous_yaw_degrees),
            0.0,
            0,
            0,
            1,
        });
    }
    return rows;
}

void write_angles_discrete(std::ostream& output, const ExactInput& input, const std::vector<int>& yaw_indices) {
    output << "  \"angles_discrete\": [\n";
    for (int index = 0; index < input.n; ++index) {
        const int yaw_index = yaw_indices.at(static_cast<std::size_t>(index));
        output << "    { \"tick\": " << index
               << ", \"yaw_index\": " << yaw_index
               << ", \"pitch_index\": 0"
               << ", \"yaw_degrees\": " << json_number(index_to_degrees(yaw_index))
               << ", \"pitch_degrees\": 0 }";
        output << (index + 1 == input.n ? "\n" : ",\n");
    }
    output << "  ],\n";
}

void write_states_exact(std::ostream& output, const std::vector<State>& states) {
    output << "  \"states_exact\": [\n";
    for (std::size_t index = 0; index < states.size(); ++index) {
        const State& state = states[index];
        output << "    { \"tick\": " << state.tick
               << ", \"position\": { \"x\": \"" << number_string(state.x)
               << "\", \"y\": \"0\", \"z\": \"" << number_string(state.z)
               << "\" }, \"velocity\": { \"x\": \"" << number_string(state.move_vx)
               << "\", \"y\": \"0\", \"z\": \"" << number_string(state.move_vz)
               << "\" }, \"on_ground\": false }";
        output << (index + 1 == states.size() ? "\n" : ",\n");
    }
    output << "  ],\n";
}

void write_macro_rows(std::ostream& output, const ExactInput& input, const std::vector<int>& yaw_indices) {
    const std::vector<MacroRow> rows = build_macro_rows(input, yaw_indices);
    output << "  \"macro_rows\": [\n";
    for (std::size_t index = 0; index < rows.size(); ++index) {
        const MacroRow& row = rows[index];
        output << "    { \"w\": " << (row.controls.forward > 0 ? "true" : "false")
               << ", \"a\": " << (row.controls.strafe > 0 ? "true" : "false")
               << ", \"s\": " << (row.controls.forward < 0 ? "true" : "false")
               << ", \"d\": " << (row.controls.strafe < 0 ? "true" : "false")
               << ", \"p\": " << (row.controls.sprint ? "true" : "false")
               << ", \"n\": " << (row.controls.sneak ? "true" : "false")
               << ", \"j\": " << (row.controls.jump ? "true" : "false")
               << ", \"yaw\": " << json_number(row.yaw)
               << ", \"pitch\": " << json_number(row.pitch)
               << ", \"l\": " << row.left_click
               << ", \"r\": " << row.right_click
               << ", \"count\": " << row.count << " }";
        output << (index + 1 == rows.size() ? "\n" : ",\n");
    }
    output << "  ],\n";
}

void write_changed_angle_indices(
    std::ostream& output,
    const ExactInput& input,
    const std::vector<int>& yaw_indices) {
    bool first_change = true;
    const std::vector<int> initial_yaw_indices = seed_yaw_indices(input);
    for (int index = 0; index < input.n; ++index) {
        const int before = initial_yaw_indices.at(static_cast<std::size_t>(index));
        const int after = yaw_indices.at(static_cast<std::size_t>(index));
        if (before == after) {
            continue;
        }
        if (!first_change) {
            output << ", ";
        }
        int delta = (after - before + 32768) & 65535;
        delta -= 32768;
        first_change = false;
        output << "{ \"slot\": " << (index + 1)
               << ", \"from\": " << before
               << ", \"to\": " << after
               << ", \"delta\": " << delta << " }";
    }
}

void write_diagnostics(
    std::ostream& output,
    const ExactInput& input,
    const RepairResult& repair_result,
    const std::vector<State>& states,
    const std::vector<int>& yaw_indices) {
    output << "  \"diagnostics\": { \"mode\": \"exact_solver_input_v1\", \"state_count\": "
           << states.size()
           << ", \"initial_residual_norm\": \"" << number_string(repair_result.initial.residual_norm)
           << "\", \"final_residual_norm\": \"" << number_string(repair_result.final.residual_norm)
           << "\", \"worst_constraint_id\": \"" << repair_result.final.worst_constraint_id
           << "\", \"candidate_evaluations\": " << repair_result.candidate_evaluations
           << ", \"repair_iterations\": " << repair_result.repair_iterations
           << ", \"exact_objective_value\": \"" << number_string(repair_result.final.objective_value)
           << "\", \"objective_deviation\": \"" << number_string(repair_result.final.objective_deviation)
           << "\", \"changed_angle_indices\": [";
    write_changed_angle_indices(output, input, yaw_indices);
    output << "] }\n";
}

} // namespace

void write_solution_json(std::ostream& output, const ExactInput& input, const RepairResult& repair_result) {
    const std::vector<State>& states = repair_result.final.states;
    const std::vector<int>& yaw_indices = repair_result.yaw_indices;

    output << "{\n";
    output << "  \"version\": 1,\n";
    output << "  \"status\": \"" << (repair_result.final.feasible ? "solved" : "failed") << "\",\n";
    write_angles_discrete(output, input, yaw_indices);
    write_states_exact(output, states);
    write_macro_rows(output, input, yaw_indices);
    write_diagnostics(output, input, repair_result, states, yaw_indices);
    output << "}\n";
}

void write_macro_csv(std::ostream& output, const ExactInput& input, const RepairResult& repair_result) {
    const std::vector<MacroRow> rows = build_macro_rows(input, repair_result.yaw_indices);
    output << "W,A,S,D,P,N,J,YAW,PITCH,L,R,COUNT\n";
    for (const MacroRow& row : rows) {
        output << (row.controls.forward > 0 ? "true" : "false") << ","
               << (row.controls.strafe > 0 ? "true" : "false") << ","
               << (row.controls.forward < 0 ? "true" : "false") << ","
               << (row.controls.strafe < 0 ? "true" : "false") << ","
               << (row.controls.sprint ? "true" : "false") << ","
               << (row.controls.sneak ? "true" : "false") << ","
               << (row.controls.jump ? "true" : "false") << ","
               << json_number(row.yaw) << ","
               << json_number(row.pitch) << ","
               << row.left_click << ","
               << row.right_click << ","
               << row.count << "\n";
    }
}

} // namespace wolframtas
