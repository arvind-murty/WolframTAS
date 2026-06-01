#include "wolframtas/exact_movement.hpp"

#include "wolframtas/angle_table.hpp"

#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <vector>

namespace wolframtas {
namespace {

struct SlotMovement {
    double imux = 0.0;
    double imuz = 0.0;
    double mmu = 0.0;
};

float no45_forward_acceleration(float movement) {
    const float forward = static_cast<float>(1.0F * 0.98F);
    float distance = static_cast<float>(forward * forward);
    distance = static_cast<float>(std::sqrt(static_cast<double>(distance)));
    if (distance < 1.0F) {
        distance = 1.0F;
    }
    distance = static_cast<float>(movement / distance);
    return static_cast<float>(forward * distance);
}

double movement_acceleration(float movement, const MovementSlot& slot) {
    if (slot.acceleration_input == "no45_forward") {
        if (slot.controls.forward != 1 || slot.controls.strafe != 0) {
            throw std::runtime_error("no45_forward requires forward=1 and strafe=0");
        }
        return static_cast<double>(no45_forward_acceleration(movement));
    }
    if (slot.acceleration_input == "forward_45") {
        if (slot.controls.forward != 1 || std::abs(slot.controls.strafe) != 1) {
            throw std::runtime_error("forward_45 requires forward=1 and abs(strafe)=1");
        }
        return static_cast<double>(movement);
    }
    throw std::runtime_error("unsupported movement input mode: " + slot.acceleration_input);
}

float retention_multiplier(const std::string& medium) {
    if (medium == "flat_ground") {
        return static_cast<float>(0.91F * 0.6F);
    }
    if (medium == "air") {
        return static_cast<float>(0.91F * 1.0F);
    }
    if (medium == "slime") {
        return static_cast<float>(0.91F * 0.8F);
    }
    if (medium == "ice") {
        return static_cast<float>(0.91F * 0.98F);
    }
    if (medium == "water") {
        const float water_slip = static_cast<float>(0.8F / 0.91F);
        return static_cast<float>(0.91F * water_slip);
    }
    if (medium == "lava") {
        const float lava_slip = static_cast<float>(0.5F / 0.91F);
        return static_cast<float>(0.91F * lava_slip);
    }
    if (medium == "none") {
        return 0.0F;
    }
    throw std::runtime_error("unsupported retention medium: " + medium);
}

SlotMovement derive_slot_movement(const MovementSlot& slot) {
    if (slot.kind == "init") {
        return SlotMovement{
            slot.init_imux,
            slot.init_imuz,
            slot.init_speed,
        };
    }

    float retention_x = retention_multiplier(slot.retention_medium);
    float retention_z = retention_x;
    if (slot.wall_hit_x) {
        retention_x = 0.0F;
    }
    if (slot.wall_hit_z) {
        retention_z = 0.0F;
    }
    if (slot.controls.forward == 0 && slot.controls.strafe == 0) {
        return SlotMovement{static_cast<double>(retention_x), static_cast<double>(retention_z), 0.0};
    }
    float movement = 0.0F;
    if (slot.acceleration_medium == "ground") {
        movement = 0.1F;
        if (slot.controls.sprint) {
            movement = static_cast<float>(static_cast<double>(movement) * (1.0 + static_cast<double>(0.3F)));
        }
        const float retention = retention_multiplier(slot.retention_medium);
        movement = static_cast<float>(
            movement * static_cast<float>(0.16277136F / static_cast<float>(retention * retention * retention)));
    } else if (slot.acceleration_medium == "air") {
        movement = 0.02F;
        if (slot.controls.sprint) {
            movement = static_cast<float>(static_cast<double>(movement) + static_cast<double>(movement) * 0.3);
        }
    } else if (slot.acceleration_medium == "water" || slot.acceleration_medium == "lava") {
        movement = 0.02F;
    } else {
        throw std::runtime_error("unsupported movement slot acceleration medium: " + slot.acceleration_medium);
    }

    double mmu = movement_acceleration(movement, slot);
    if (slot.acceleration_medium == "ground" && slot.controls.jump && slot.controls.sprint) {
        mmu += static_cast<double>(0.2F);
    }
    return SlotMovement{static_cast<double>(retention_x), static_cast<double>(retention_z), mmu};
}

float mcsin_index(int index) {
    return static_cast<float>(
        std::sin(static_cast<double>(index & 65535) * 3.14159265358979323846 * 2.0 / 65536.0));
}

float mccos_index(int index) {
    return mcsin_index(index + 16384);
}

int mc_angle_index_from_radians(double radians) {
    return static_cast<int>(static_cast<float>(radians) * static_cast<float>(10430.378)) & 65535;
}

double yaw_index_to_movement_radians(int yaw_index) {
    return -index_to_degrees(yaw_index) * 3.14159265358979323846 / 180.0;
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

} // namespace

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
        const SlotMovement movement = derive_slot_movement(slot);
        input.imux.push_back(movement.imux);
        input.imuz.push_back(movement.imuz);
        input.mmu.push_back(movement.mmu);
    }
}

void validate_exact_input(const ExactInput& input) {
    if (input.movement_slots.size() < static_cast<std::size_t>(input.n)) {
        throw std::runtime_error("movement_plan.slots must contain at least n values");
    }
    if (input.imux.size() < static_cast<std::size_t>(input.n)
        || input.imuz.size() < static_cast<std::size_t>(input.n)
        || input.mmu.size() < static_cast<std::size_t>(input.n)) {
        throw std::runtime_error("movement_plan must derive at least n movement values");
    }
}

std::vector<int> seed_yaw_indices(const ExactInput& input) {
    std::vector<int> yaw_indices;
    yaw_indices.reserve(static_cast<std::size_t>(input.n));
    for (int index = 0; index < input.n; ++index) {
        const double yaw_radians = -input.movement_direction_radians.at(static_cast<std::size_t>(index));
        yaw_indices.push_back(mc_angle_index_from_radians(yaw_radians));
    }
    return yaw_indices;
}

std::vector<State> simulate(const ExactInput& input, const std::vector<int>& yaw_indices) {
    constexpr double inertia_threshold = 0.005;
    std::vector<State> states;
    State state = input.initial_state;
    states.push_back(state);

    for (int index = 0; index < input.n; ++index) {
        const int slot = index + 1;
        const auto offset = static_cast<std::size_t>(index);
        const int yaw_index = yaw_indices.at(offset);
        const double movement_direction = yaw_index_to_movement_radians(yaw_index);
        const double imux = input.imux.at(offset);
        const double imuz = input.imuz.at(offset);
        const double mmu = input.mmu.at(offset);
        const MovementSlot* movement_slot = input.movement_slots.empty() ? nullptr : &input.movement_slots.at(offset);

        double mmux = 0.0;
        double mmuz = 0.0;
        if (movement_slot != nullptr && movement_slot->kind == "init") {
            mmux = std::sin(movement_direction) * mmu;
            mmuz = std::cos(movement_direction) * mmu;
        } else {
            mmux = -static_cast<double>(mcsin_index(yaw_index)) * mmu;
            mmuz = static_cast<double>(mccos_index(yaw_index)) * mmu;
        }
        mmux = override_component(input.component_overrides, "mmux", slot, mmux);
        mmuz = override_component(input.component_overrides, "mmuz", slot, mmuz);

        state.vx += mmux;
        state.vz += mmuz;
        state.move_vx = state.vx;
        state.move_vz = state.vz;
        state.x += state.vx;
        state.z += state.vz;
        state.vx *= imux;
        state.vz *= imuz;
        state.retained_vx = state.vx;
        state.retained_vz = state.vz;

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

} // namespace wolframtas
