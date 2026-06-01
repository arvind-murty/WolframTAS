#include "wolframtas/exact_input.hpp"

#include "wolframtas/json.hpp"

#include <cmath>
#include <stdexcept>
#include <string>
#include <variant>

namespace wolframtas {
namespace {

const Json& at(const Json::Object& object, const std::string& key) {
    const auto iter = object.find(key);
    if (iter == object.end()) {
        throw std::runtime_error("missing JSON key: " + key);
    }
    return iter->second;
}

const Json* find_value(const Json::Object& object, const std::string& key) {
    const auto iter = object.find(key);
    if (iter == object.end()) {
        return nullptr;
    }
    return &iter->second;
}

int json_int(const Json& value, const std::string& name) {
    const double number = value.number();
    const auto integer = static_cast<int>(number);
    if (std::floor(number) != number) {
        throw std::runtime_error(name + " must be an integer");
    }
    return integer;
}

bool json_bool(const Json& value, const std::string& name) {
    if (const auto* bool_value = std::get_if<bool>(&value.value)) {
        return *bool_value;
    }
    throw std::runtime_error(name + " must be a boolean");
}

double optional_number(const Json::Object& object, const std::string& key, double fallback) {
    const Json* value = find_value(object, key);
    return value == nullptr ? fallback : value->number();
}

int optional_int(const Json::Object& object, const std::string& key, int fallback) {
    const Json* value = find_value(object, key);
    return value == nullptr ? fallback : json_int(*value, key);
}

Controls parse_controls(const Json::Object& object) {
    Controls controls;
    controls.forward = json_int(at(object, "forward"), "controls.forward");
    controls.strafe = json_int(at(object, "strafe"), "controls.strafe");
    controls.jump = json_bool(at(object, "jump"), "controls.jump");
    controls.sneak = json_bool(at(object, "sneak"), "controls.sneak");
    controls.sprint = json_bool(at(object, "sprint"), "controls.sprint");
    return controls;
}

State parse_initial_state(const Json::Object& object) {
    State state;
    const Json* initial_state_value = find_value(object, "initial_state");
    if (initial_state_value == nullptr) {
        return state;
    }
    const Json::Object& initial_state = initial_state_value->object();
    const Json::Object& position = at(initial_state, "position").object();
    const Json::Object& velocity = at(initial_state, "velocity").object();
    state.x = at(position, "x").number();
    state.z = at(position, "z").number();
    state.vx = at(velocity, "x").number();
    state.vz = at(velocity, "z").number();
    return state;
}

void parse_movement_plan(const Json::Object& object, ExactInput& exact_input) {
    const Json* movement_plan_value = find_value(object, "movement_plan");
    if (movement_plan_value == nullptr) {
        return;
    }

    const Json::Object& movement_plan = movement_plan_value->object();
    for (const Json& item : at(movement_plan, "slots").array()) {
        const Json::Object& slot_object = item.object();
        MovementSlot slot;
        slot.slot = json_int(at(slot_object, "slot"), "movement slot");
        const Json* kind_value = find_value(slot_object, "kind");
        if (kind_value != nullptr) {
            slot.kind = kind_value->string();
        }
        if (slot.kind == "init") {
            slot.init_speed = at(slot_object, "speed").number();
            slot.init_imux = at(slot_object, "imux").number();
            slot.init_imuz = at(slot_object, "imuz").number();
        } else {
            const Json::Object& acceleration = at(slot_object, "acceleration").object();
            const Json::Object& retention = at(slot_object, "retention").object();
            slot.controls = parse_controls(at(slot_object, "controls").object());
            slot.acceleration_medium = at(acceleration, "medium").string();
            const Json* input_mode = find_value(acceleration, "input");
            if (input_mode != nullptr) {
                slot.acceleration_input = input_mode->string();
            }
            slot.retention_medium = at(retention, "medium").string();
            const Json* web_value = find_value(slot_object, "web");
            if (web_value != nullptr) {
                slot.web = json_bool(*web_value, "web");
            }
            const Json* ladder_value = find_value(slot_object, "ladder");
            if (ladder_value != nullptr) {
                slot.ladder = json_bool(*ladder_value, "ladder");
            }
            const Json* wall_hit = find_value(slot_object, "wall_hit");
            if (wall_hit != nullptr) {
                const Json::Object& wall_hit_object = wall_hit->object();
                for (const Json& axis_value : at(wall_hit_object, "axes").array()) {
                    const std::string axis = axis_value.string();
                    if (axis == "x") {
                        slot.wall_hit_x = true;
                    } else if (axis == "z") {
                        slot.wall_hit_z = true;
                    } else {
                        throw std::runtime_error("wall_hit axis must be x or z");
                    }
                }
            }
        }
        const Json* slot_overrides = find_value(slot_object, "component_overrides");
        if (slot_overrides != nullptr) {
            for (const Json& override_item : slot_overrides->array()) {
                const Json::Object& override_object = override_item.object();
                exact_input.component_overrides.push_back(
                    ComponentOverride{
                        at(override_object, "target").string(),
                        slot.slot,
                        at(override_object, "value").number(),
                    });
            }
        }
        exact_input.movement_slots.push_back(slot);
    }
}

void parse_inertia_events(const Json::Object& object, ExactInput& exact_input) {
    const Json* events_value = find_value(object, "inertia_events");
    if (events_value == nullptr) {
        const Json* derived_model_value = find_value(object, "derived_model");
        if (derived_model_value != nullptr) {
            events_value = find_value(derived_model_value->object(), "inertia_events");
        }
    }
    if (events_value == nullptr) {
        return;
    }

    for (const Json& item : events_value->array()) {
        const Json::Object& event = item.object();
        InertiaEvent parsed;
        parsed.id = at(event, "id").string();
        parsed.type = at(event, "type").string();
        if (parsed.type != "hit" && parsed.type != "avoid") {
            throw std::runtime_error("inertia_events.type must be hit or avoid");
        }
        parsed.axis = at(event, "axis").string();
        if (parsed.axis != "x" && parsed.axis != "z") {
            throw std::runtime_error("inertia_events.axis must be x or z");
        }
        parsed.slot = json_int(at(event, "slot"), "inertia_events.slot");
        parsed.threshold = optional_number(event, "threshold", parsed.threshold);
        const Json* direction = find_value(event, "direction");
        if (direction != nullptr) {
            parsed.direction = direction->string();
        }
        if (parsed.type == "avoid" && parsed.direction != "positive" && parsed.direction != "negative") {
            throw std::runtime_error("inertia_events.direction must be positive or negative for avoid");
        }
        exact_input.inertia_events.push_back(parsed);
    }
}

void parse_position_bound(const Json::Object& object, const std::string& key, bool& present, double& value) {
    const Json* bound = find_value(object, key);
    if (bound == nullptr) {
        return;
    }
    present = true;
    value = bound->number();
}

void parse_constraints(const Json::Object& object, ExactInput& exact_input) {
    const Json* constraints_value = find_value(object, "constraints");
    if (constraints_value == nullptr) {
        const Json* derived_model_value = find_value(object, "derived_model");
        if (derived_model_value != nullptr) {
            constraints_value = find_value(derived_model_value->object(), "constraints");
        }
    }
    if (constraints_value == nullptr) {
        return;
    }

    for (const Json& item : constraints_value->array()) {
        const Json::Object& constraint = item.object();
        const std::string type = at(constraint, "type").string();
        if (type != "position_bounds") {
            throw std::runtime_error("unsupported exact constraint type: " + type);
        }

        PositionConstraint parsed;
        parsed.id = at(constraint, "id").string();
        parsed.slot = json_int(at(constraint, "slot"), "constraint.slot");
        parsed.exact_tolerance = optional_number(constraint, "exact_tolerance", parsed.exact_tolerance);
        parse_position_bound(constraint, "min_x", parsed.has_min_x, parsed.min_x);
        parse_position_bound(constraint, "max_x", parsed.has_max_x, parsed.max_x);
        parse_position_bound(constraint, "min_z", parsed.has_min_z, parsed.min_z);
        parse_position_bound(constraint, "max_z", parsed.has_max_z, parsed.max_z);
        if (!parsed.has_min_x && !parsed.has_max_x && !parsed.has_min_z && !parsed.has_max_z) {
            throw std::runtime_error("position_bounds constraint must set at least one bound");
        }
        exact_input.constraints.push_back(parsed);
    }
}

void parse_exact_objective(const Json::Object& object, ExactInput& exact_input) {
    const Json* objective_value = find_value(object, "exact_objective");
    if (objective_value == nullptr) {
        return;
    }
    const Json::Object& objective = objective_value->object();
    const std::string type = at(objective, "type").string();
    if (type != "position") {
        throw std::runtime_error("unsupported exact objective type: " + type);
    }
    exact_input.objective.enabled = true;
    exact_input.objective.axis = at(objective, "axis").string();
    if (exact_input.objective.axis != "x" && exact_input.objective.axis != "z") {
        throw std::runtime_error("exact_objective.axis must be x or z");
    }
    exact_input.objective.slot = json_int(at(objective, "slot"), "exact_objective.slot");
    const Json* target_value = find_value(objective, "target_value");
    if (target_value != nullptr) {
        exact_input.objective.target_value = target_value->number();
        exact_input.objective.target_value_set = true;
    }
    exact_input.objective.tolerance = optional_number(objective, "solution_tolerance", 0.001);
}

void parse_solver_settings(const Json::Object& object, ExactInput& exact_input) {
    const Json* settings_value = find_value(object, "exact_solver");
    if (settings_value == nullptr) {
        return;
    }
    const Json::Object& settings = settings_value->object();
    exact_input.solver_settings.max_repair_iterations =
        optional_int(settings, "max_repair_iterations", exact_input.solver_settings.max_repair_iterations);
    exact_input.solver_settings.max_candidate_evaluations =
        optional_int(settings, "max_candidate_evaluations", exact_input.solver_settings.max_candidate_evaluations);
    exact_input.solver_settings.top_k_moves =
        optional_int(settings, "top_k_moves", exact_input.solver_settings.top_k_moves);
    exact_input.solver_settings.max_index_delta_per_iteration =
        optional_int(settings, "max_index_delta_per_iteration", exact_input.solver_settings.max_index_delta_per_iteration);
}

} // namespace

ExactInput parse_exact_input(const std::string& input) {
    const Json root = JsonParser(input).parse();
    const Json::Object& object = root.object();

    ExactInput exact_input;
    exact_input.n = json_int(at(object, "n"), "n");
    exact_input.initial_state = parse_initial_state(object);
    parse_movement_plan(object, exact_input);
    parse_inertia_events(object, exact_input);
    parse_constraints(object, exact_input);
    parse_exact_objective(object, exact_input);
    parse_solver_settings(object, exact_input);

    const Json::Object& solution = at(object, "optimal_solution").object();
    if (exact_input.objective.enabled && !exact_input.objective.target_value_set) {
        exact_input.objective.target_value =
            optional_number(solution, "objective_value", exact_input.objective.target_value);
    }
    for (const Json& item : at(solution, "movement_directions").array()) {
        const Json::Object& direction = item.object();
        exact_input.movement_direction_radians.push_back(at(direction, "radians").number());
    }
    if (exact_input.movement_direction_radians.size() < static_cast<std::size_t>(exact_input.n)) {
        throw std::runtime_error("optimal_solution.movement_directions must contain at least n values");
    }
    if (exact_input.n <= 0) {
        throw std::runtime_error("n must be positive");
    }

    return exact_input;
}

} // namespace wolframtas
