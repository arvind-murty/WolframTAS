#include "wolframtas/angle_table.hpp"

#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>

namespace {

struct Json {
    using Array = std::vector<Json>;
    using Object = std::map<std::string, Json>;

    std::variant<std::nullptr_t, bool, double, std::string, Array, Object> value;

    const Object& object() const {
        if (const auto* object_value = std::get_if<Object>(&value)) {
            return *object_value;
        }
        throw std::runtime_error("expected JSON object");
    }

    const Array& array() const {
        if (const auto* array_value = std::get_if<Array>(&value)) {
            return *array_value;
        }
        throw std::runtime_error("expected JSON array");
    }

    const std::string& string() const {
        if (const auto* string_value = std::get_if<std::string>(&value)) {
            return *string_value;
        }
        throw std::runtime_error("expected JSON string");
    }

    double number() const {
        if (const auto* number_value = std::get_if<double>(&value)) {
            return *number_value;
        }
        throw std::runtime_error("expected JSON number");
    }
};

class JsonParser {
public:
    explicit JsonParser(std::string input) : input_(std::move(input)) {}

    Json parse() {
        Json value = parse_value();
        skip_ws();
        if (position_ != input_.size()) {
            throw std::runtime_error("unexpected trailing JSON input");
        }
        return value;
    }

private:
    Json parse_value() {
        skip_ws();
        if (position_ >= input_.size()) {
            throw std::runtime_error("unexpected end of JSON input");
        }
        const char ch = input_[position_];
        if (ch == '{') {
            return Json{parse_object()};
        }
        if (ch == '[') {
            return Json{parse_array()};
        }
        if (ch == '"') {
            return Json{parse_string()};
        }
        if (ch == '-' || (ch >= '0' && ch <= '9')) {
            return Json{parse_number()};
        }
        if (consume_literal("true")) {
            return Json{true};
        }
        if (consume_literal("false")) {
            return Json{false};
        }
        if (consume_literal("null")) {
            return Json{nullptr};
        }
        throw std::runtime_error("invalid JSON value");
    }

    Json::Object parse_object() {
        expect('{');
        Json::Object object;
        skip_ws();
        if (peek('}')) {
            expect('}');
            return object;
        }
        while (true) {
            skip_ws();
            const std::string key = parse_string();
            skip_ws();
            expect(':');
            object.emplace(key, parse_value());
            skip_ws();
            if (peek('}')) {
                expect('}');
                return object;
            }
            expect(',');
        }
    }

    Json::Array parse_array() {
        expect('[');
        Json::Array array;
        skip_ws();
        if (peek(']')) {
            expect(']');
            return array;
        }
        while (true) {
            array.push_back(parse_value());
            skip_ws();
            if (peek(']')) {
                expect(']');
                return array;
            }
            expect(',');
        }
    }

    std::string parse_string() {
        expect('"');
        std::string output;
        while (position_ < input_.size()) {
            const char ch = input_[position_++];
            if (ch == '"') {
                return output;
            }
            if (ch != '\\') {
                output.push_back(ch);
                continue;
            }
            if (position_ >= input_.size()) {
                throw std::runtime_error("unterminated JSON escape");
            }
            const char escaped = input_[position_++];
            switch (escaped) {
                case '"':
                case '\\':
                case '/':
                    output.push_back(escaped);
                    break;
                case 'b':
                    output.push_back('\b');
                    break;
                case 'f':
                    output.push_back('\f');
                    break;
                case 'n':
                    output.push_back('\n');
                    break;
                case 'r':
                    output.push_back('\r');
                    break;
                case 't':
                    output.push_back('\t');
                    break;
                default:
                    throw std::runtime_error("unsupported JSON string escape");
            }
        }
        throw std::runtime_error("unterminated JSON string");
    }

    double parse_number() {
        const char* start = input_.c_str() + position_;
        char* end = nullptr;
        const double value = std::strtod(start, &end);
        if (end == start) {
            throw std::runtime_error("invalid JSON number");
        }
        position_ = static_cast<std::size_t>(end - input_.c_str());
        return value;
    }

    void skip_ws() {
        while (position_ < input_.size()) {
            const char ch = input_[position_];
            if (ch != ' ' && ch != '\n' && ch != '\r' && ch != '\t') {
                break;
            }
            ++position_;
        }
    }

    bool consume_literal(const std::string& literal) {
        if (input_.compare(position_, literal.size(), literal) != 0) {
            return false;
        }
        position_ += literal.size();
        return true;
    }

    bool peek(char expected) const {
        return position_ < input_.size() && input_[position_] == expected;
    }

    void expect(char expected) {
        skip_ws();
        if (position_ >= input_.size() || input_[position_] != expected) {
            throw std::runtime_error(std::string("expected JSON character: ") + expected);
        }
        ++position_;
    }

    std::string input_;
    std::size_t position_ = 0;
};

struct ComponentOverride {
    std::string target;
    int slot = 0;
    double value = 0.0;
};

struct Controls {
    int forward = 0;
    int strafe = 0;
    bool jump = false;
    bool sneak = false;
    bool sprint = false;
};

struct MovementSlot {
    int slot = 0;
    std::string kind = "movement";
    Controls controls;
    std::string acceleration_medium;
    std::string retention_medium;
    double init_vx = 0.0;
    double init_vz = 0.0;
    double init_imux = 0.0;
    double init_imuz = 0.0;
};

struct State {
    int tick = 0;
    double x = 0.0;
    double z = 0.0;
    double vx = 0.0;
    double vz = 0.0;
};

struct ExactInput {
    int n = 0;
    State initial_state;
    std::vector<double> imux;
    std::vector<double> imuz;
    std::vector<double> mmu;
    std::vector<double> movement_direction_radians;
    std::vector<ComponentOverride> component_overrides;
    std::vector<MovementSlot> movement_slots;
};

std::string read_stdin() {
    std::ostringstream buffer;
    buffer << std::cin.rdbuf();
    return buffer.str();
}

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

std::vector<double> number_array(const Json& value) {
    std::vector<double> numbers;
    for (const Json& item : value.array()) {
        numbers.push_back(item.number());
    }
    return numbers;
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
            const Json::Object& velocity = at(slot_object, "velocity").object();
            slot.init_vx = at(velocity, "x").number();
            slot.init_vz = at(velocity, "z").number();
            slot.init_imux = at(slot_object, "imux").number();
            slot.init_imuz = at(slot_object, "imuz").number();
        } else {
            const Json::Object& acceleration = at(slot_object, "acceleration").object();
            const Json::Object& retention = at(slot_object, "retention").object();
            slot.controls = parse_controls(at(slot_object, "controls").object());
            slot.acceleration_medium = at(acceleration, "medium").string();
            slot.retention_medium = at(retention, "medium").string();
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

ExactInput parse_exact_input(const std::string& input) {
    const Json root = JsonParser(input).parse();
    const Json::Object& object = root.object();

    ExactInput exact_input;
    exact_input.n = json_int(at(object, "n"), "n");
    exact_input.initial_state = parse_initial_state(object);
    parse_movement_plan(object, exact_input);

    const Json* arrays_value = find_value(object, "arrays");
    if (arrays_value == nullptr) {
        const Json* derived_model_value = find_value(object, "derived_model");
        if (derived_model_value != nullptr) {
            const Json::Object& derived_model = derived_model_value->object();
            arrays_value = find_value(derived_model, "arrays");
        }
    }
    if (arrays_value != nullptr) {
        const Json::Object& arrays = arrays_value->object();
        exact_input.imux = number_array(at(arrays, "imux"));
        exact_input.imuz = number_array(at(arrays, "imuz"));
        exact_input.mmu = number_array(at(arrays, "mmu"));
    }

    const Json* overrides_value = find_value(object, "component_overrides");
    if (overrides_value == nullptr) {
        const Json* derived_model_value = find_value(object, "derived_model");
        if (derived_model_value != nullptr) {
            overrides_value = find_value(derived_model_value->object(), "component_overrides");
        }
    }
    if (overrides_value != nullptr) {
        for (const Json& item : overrides_value->array()) {
            const Json::Object& override_object = item.object();
            exact_input.component_overrides.push_back(
                ComponentOverride{
                    at(override_object, "target").string(),
                    json_int(at(override_object, "slot"), "component override slot"),
                    at(override_object, "value").number(),
                });
        }
    }

    const Json::Object& solution = at(object, "optimal_solution").object();
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

bool approximately(double actual, double expected) {
    return std::abs(actual - expected) <= 1e-9;
}

float reference_no45_forward_acceleration(float movement) {
    // player.py:
    //   forward *= fl(0.98)
    //   distance = fl(strafe * strafe + forward * forward)
    //   distance = fl(math.sqrt(float(distance)))
    //   if distance < fl(1.0): distance = fl(1.0)
    //   distance = movement / distance
    //   forward = forward * distance
    // with forward=1 and strafe=0.
    const float forward = static_cast<float>(1.0F * 0.98F);
    float distance = static_cast<float>(forward * forward);
    distance = static_cast<float>(std::sqrt(static_cast<double>(distance)));
    if (distance < 1.0F) {
        distance = 1.0F;
    }
    distance = static_cast<float>(movement / distance);
    return static_cast<float>(forward * distance);
}

float reference_flat_ground_retention() {
    // player.py finalizes momentum as:
    //   self.vx *= fl(0.91) * self.prev_slip
    // and flat ground initializes slip from:
    //   self.ground_slip = fl(0.6)
    return static_cast<float>(0.91F * 0.6F);
}

float reference_air_retention() {
    // Airborne slip is fl(1), so fl(0.91) * fl(1) is the retained multiplier.
    return static_cast<float>(0.91F * 1.0F);
}

float reference_water_retention() {
    // Water uses slip = fl(0.8/0.91), then final momentum multiplies by fl(0.91).
    const float water_slip = static_cast<float>(0.8F / 0.91F);
    return static_cast<float>(0.91F * water_slip);
}

double reference_flat_sprint_jump_no45_mmu() {
    // player.py ground movement path:
    //   movement = fl(0.1)
    //   if sprinting: movement = fl(movement * (1.0 + fl(0.3)))
    //   drag = fl(0.91) * slip
    //   movement *= fl(0.16277136) / (drag * drag * drag)
    // then the no-45 forward acceleration path contributes forward*movement,
    // and sprintjump adds mccos(0)*fl(0.2) on +Z.
    float movement = 0.1F;
    movement = static_cast<float>(static_cast<double>(movement) * (1.0 + static_cast<double>(0.3F)));
    const float drag = reference_flat_ground_retention();
    movement = static_cast<float>(movement * static_cast<float>(0.16277136F / static_cast<float>(drag * drag * drag)));
    const float normal_acceleration = reference_no45_forward_acceleration(movement);
    return static_cast<double>(normal_acceleration) + static_cast<double>(0.2F);
}

double reference_air_sprint_no45_mmu() {
    // player.py air movement path:
    //   movement = fl(0.02)
    //   if delayed sprint applies: movement = fl(movement + movement * 0.3)
    // followed by the no-45 forward acceleration path.
    float movement = 0.02F;
    movement = static_cast<float>(static_cast<double>(movement) + static_cast<double>(movement) * 0.3);
    return static_cast<double>(reference_no45_forward_acceleration(movement));
}

double reference_air_walk_no45_mmu() {
    // Airborne no-sprint movement starts from fl(0.02), followed by no-45 input.
    return static_cast<double>(reference_no45_forward_acceleration(0.02F));
}

double reference_flat_walk_no45_mmu() {
    // Flat no-sprint movement starts from fl(0.1), followed by no-45 input.
    return static_cast<double>(reference_no45_forward_acceleration(0.1F));
}

float canonical_im(double value) {
    if (approximately(value, 0.546)) {
        return reference_flat_ground_retention();
    }
    if (approximately(value, 0.91)) {
        return reference_air_retention();
    }
    if (approximately(value, 0.8)) {
        return reference_water_retention();
    }
    if (approximately(value, 0.0)) {
        return 0.0F;
    }
    return static_cast<float>(value);
}

double canonical_mmu(double value) {
    if (approximately(value, 0.3274)) {
        return reference_flat_sprint_jump_no45_mmu();
    }
    if (approximately(value, 0.02548)) {
        return reference_air_sprint_no45_mmu();
    }
    if (approximately(value, 0.0196)) {
        return reference_air_walk_no45_mmu();
    }
    if (approximately(value, 0.098)) {
        return reference_flat_walk_no45_mmu();
    }
    if (approximately(value, 0.0)) {
        return 0.0;
    }
    return value;
}

void normalize_exact_input(ExactInput& input) {
    // The JSON fixtures use short human-readable values like 0.3274 and 0.546.
    // This pass validates their known provenance and rewrites them to the
    // float32 values produced by the anon-noob mothball player.py operation
    // paths above before the hot simulation loop runs.
    for (int index = 0; index < input.n; ++index) {
        const auto offset = static_cast<std::size_t>(index);
        input.imux[offset] = static_cast<double>(canonical_im(input.imux[offset]));
        input.imuz[offset] = static_cast<double>(canonical_im(input.imuz[offset]));
        input.mmu[offset] = canonical_mmu(input.mmu[offset]);
    }
}

double derive_retention(const MovementSlot& slot) {
    if (slot.kind == "init") {
        throw std::runtime_error("init slots use explicit imux/imuz");
    }
    if (slot.retention_medium == "flat_ground") {
        return static_cast<double>(reference_flat_ground_retention());
    }
    if (slot.retention_medium == "air") {
        return static_cast<double>(reference_air_retention());
    }
    if (slot.retention_medium == "water") {
        return static_cast<double>(reference_water_retention());
    }
    if (slot.retention_medium == "none") {
        return 0.0;
    }
    throw std::runtime_error("unsupported retention medium: " + slot.retention_medium);
}

double derive_mmu(const MovementSlot& slot) {
    if (slot.kind == "init") {
        return 0.0;
    }
    if (slot.controls.forward == 0 && slot.controls.strafe == 0) {
        return 0.0;
    }
    if (slot.controls.forward != 1 || slot.controls.strafe != 0) {
        throw std::runtime_error("movement-plan v1 only supports no-45 forward movement");
    }
    if (slot.acceleration_medium == "ground") {
        if (slot.controls.sprint && slot.controls.jump) {
            return reference_flat_sprint_jump_no45_mmu();
        }
        if (!slot.controls.sprint) {
            return reference_flat_walk_no45_mmu();
        }
    }
    if (slot.acceleration_medium == "air") {
        return slot.controls.sprint ? reference_air_sprint_no45_mmu() : reference_air_walk_no45_mmu();
    }
    throw std::runtime_error("unsupported movement slot acceleration medium: " + slot.acceleration_medium);
}

void derive_arrays_from_movement_plan(ExactInput& input) {
    if (input.movement_slots.empty()) {
        return;
    }
    if (input.movement_slots.size() < static_cast<std::size_t>(input.n)) {
        throw std::runtime_error("movement_plan.slots must contain at least n values");
    }

    input.imux.clear();
    input.imuz.clear();
    input.mmu.clear();
    for (int index = 0; index < input.n; ++index) {
        const MovementSlot& slot = input.movement_slots.at(static_cast<std::size_t>(index));
        if (slot.slot != index + 1) {
            throw std::runtime_error("movement_plan.slots must be in 1-based slot order");
        }
        if (slot.kind == "init") {
            input.imux.push_back(slot.init_imux);
            input.imuz.push_back(slot.init_imuz);
            input.mmu.push_back(std::hypot(slot.init_vx, slot.init_vz));
            continue;
        }
        const double retention = derive_retention(slot);
        input.imux.push_back(retention);
        input.imuz.push_back(retention);
        input.mmu.push_back(derive_mmu(slot));
    }
}

void prepare_exact_input(ExactInput& input) {
    if (!input.movement_slots.empty()) {
        derive_arrays_from_movement_plan(input);
    } else {
        if (input.imux.size() < static_cast<std::size_t>(input.n)
            || input.imuz.size() < static_cast<std::size_t>(input.n)
            || input.mmu.size() < static_cast<std::size_t>(input.n)) {
            throw std::runtime_error("movement plan or arrays must provide at least n movement values");
        }
        normalize_exact_input(input);
    }
    if (input.imux.size() < static_cast<std::size_t>(input.n)
        || input.imuz.size() < static_cast<std::size_t>(input.n)
        || input.mmu.size() < static_cast<std::size_t>(input.n)) {
        throw std::runtime_error("movement plan or arrays must provide at least n movement values");
    }
}

float mcsin(double radians) {
    const int index = static_cast<int>(static_cast<float>(radians) * static_cast<float>(10430.378)) & 65535;
    return static_cast<float>(std::sin(static_cast<double>(index) * 3.14159265358979323846 * 2.0 / 65536.0));
}

float mccos(double radians) {
    const int index = static_cast<int>(
                          static_cast<float>(radians) * static_cast<float>(10430.378)
                          + static_cast<float>(16384.0))
        & 65535;
    return static_cast<float>(std::sin(static_cast<double>(index) * 3.14159265358979323846 * 2.0 / 65536.0));
}

int mc_angle_index_from_radians(double radians) {
    return static_cast<int>(static_cast<float>(radians) * static_cast<float>(10430.378)) & 65535;
}

double radians_to_degrees(double radians) {
    return radians * 180.0 / 3.14159265358979323846;
}

double override_component(
    const std::vector<ComponentOverride>& overrides,
    const std::string& target,
    int slot,
    double fallback) {
    for (const ComponentOverride& override : overrides) {
        if (override.target == target && override.slot == slot) {
            return override.value;
        }
    }
    return fallback;
}

std::vector<State> simulate(const ExactInput& input) {
    constexpr double inertia_threshold = 0.005;
    std::vector<State> states;
    State state = input.initial_state;
    states.push_back(state);

    for (int index = 0; index < input.n; ++index) {
        const int slot = index + 1;
        const double yaw_radians = -input.movement_direction_radians.at(static_cast<std::size_t>(index));
        const double imux = input.imux.at(static_cast<std::size_t>(index));
        const double imuz = input.imuz.at(static_cast<std::size_t>(index));
        const double mmu = input.mmu.at(static_cast<std::size_t>(index));

        double mmux = -static_cast<double>(mcsin(yaw_radians)) * mmu;
        double mmuz = static_cast<double>(mccos(yaw_radians)) * mmu;
        mmux = override_component(input.component_overrides, "mmux", slot, mmux);
        mmuz = override_component(input.component_overrides, "mmuz", slot, mmuz);

        state.vx += mmux;
        state.vz += mmuz;
        state.x += state.vx;
        state.z += state.vz;
        state.vx *= imux;
        state.vz *= imuz;

        if (std::abs(state.vx) < inertia_threshold) {
            state.vx = 0.0;
        }
        if (std::abs(state.vz) < inertia_threshold) {
            state.vz = 0.0;
        }
        state.tick = slot;
        states.push_back(state);
    }

    return states;
}

std::string number_string(double value) {
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

} // namespace

int main() {
    const std::string input = read_stdin();
    if (input.empty()) {
        std::cerr << "wolframtas_solver expected exact-solver input JSON on stdin\n";
        return 1;
    }

    try {
        ExactInput exact_input = parse_exact_input(input);
        prepare_exact_input(exact_input);
        const std::vector<State> states = simulate(exact_input);

        std::cout << "{\n";
        std::cout << "  \"version\": 1,\n";
        std::cout << "  \"status\": \"solved\",\n";
        std::cout << "  \"angles_discrete\": [\n";
        for (int index = 0; index < exact_input.n; ++index) {
            const double yaw_radians = -exact_input.movement_direction_radians.at(static_cast<std::size_t>(index));
            const int yaw_index = mc_angle_index_from_radians(yaw_radians);
            std::cout << "    { \"tick\": " << index
                      << ", \"yaw_index\": " << yaw_index
                      << ", \"pitch_index\": 0"
                      << ", \"yaw_degrees\": " << json_number(wolframtas::index_to_degrees(yaw_index))
                      << ", \"pitch_degrees\": 0 }";
            std::cout << (index + 1 == exact_input.n ? "\n" : ",\n");
        }
        std::cout << "  ],\n";

        std::cout << "  \"states_exact\": [\n";
        for (std::size_t index = 0; index < states.size(); ++index) {
            const State& state = states[index];
            std::cout << "    { \"tick\": " << state.tick
                      << ", \"position\": { \"x\": \"" << number_string(state.x)
                      << "\", \"y\": \"0\", \"z\": \"" << number_string(state.z)
                      << "\" }, \"velocity\": { \"x\": \"" << number_string(state.vx)
                      << "\", \"y\": \"0\", \"z\": \"" << number_string(state.vz)
                      << "\" }, \"on_ground\": false }";
            std::cout << (index + 1 == states.size() ? "\n" : ",\n");
        }
        std::cout << "  ],\n";

        std::cout << "  \"macro_rows\": [\n";
        for (int index = 0; index < exact_input.n; ++index) {
            const Controls controls = macro_controls_for_slot(exact_input, index);
            const double current_yaw_radians = -exact_input.movement_direction_radians.at(static_cast<std::size_t>(index));
            const double previous_yaw_radians = index == 0
                ? 0.0
                : -exact_input.movement_direction_radians.at(static_cast<std::size_t>(index - 1));
            const double relative_yaw = radians_to_degrees(current_yaw_radians - previous_yaw_radians);
            std::cout << "    { \"w\": " << (controls.forward > 0 ? "true" : "false")
                      << ", \"a\": " << (controls.strafe > 0 ? "true" : "false")
                      << ", \"s\": " << (controls.forward < 0 ? "true" : "false")
                      << ", \"d\": " << (controls.strafe < 0 ? "true" : "false")
                      << ", \"p\": " << (controls.sprint ? "true" : "false")
                      << ", \"n\": " << (controls.sneak ? "true" : "false")
                      << ", \"j\": " << (controls.jump ? "true" : "false")
                      << ", \"yaw\": " << json_number(relative_yaw)
                      << ", \"pitch\": 0, \"l\": 0, \"r\": 0, \"count\": 1 }";
            std::cout << (index + 1 == exact_input.n ? "\n" : ",\n");
        }
        std::cout << "  ],\n";
        std::cout << "  \"diagnostics\": { \"mode\": \"exact_solver_input_v1\", \"state_count\": "
                  << states.size() << " }\n";
        std::cout << "}\n";
    } catch (const std::exception& error) {
        std::cerr << "wolframtas_solver failed: " << error.what() << "\n";
        return 1;
    }

    return 0;
}
