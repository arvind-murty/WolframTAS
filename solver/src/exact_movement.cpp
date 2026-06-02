#include "wolframtas/exact_movement.hpp"

#include "wolframtas/angle_table.hpp"
#include "wolframtas/movement_constants_generated.hpp"

#include <algorithm>
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

// Retention (imu) per medium. The values are the SINGLE source of truth in
// movement_constants_generated.hpp (tools/gen_movement_constants.py, numpy
// float32); the orchestrator reads the same numbers from the JSON twin.
float retention_multiplier(const std::string& medium) {
    namespace mc = movement_constants;
    if (medium == "flat_ground") {
        return static_cast<float>(mc::RETENTION_FLAT_GROUND);
    }
    if (medium == "air") {
        return static_cast<float>(mc::RETENTION_AIR);
    }
    if (medium == "slime") {
        return static_cast<float>(mc::RETENTION_SLIME);
    }
    if (medium == "ice") {
        return static_cast<float>(mc::RETENTION_ICE);
    }
    if (medium == "water") {
        return static_cast<float>(mc::RETENTION_WATER);
    }
    if (medium == "lava") {
        return static_cast<float>(mc::RETENTION_LAVA);
    }
    if (medium == "none") {
        return static_cast<float>(mc::RETENTION_NONE);
    }
    throw std::runtime_error("unsupported retention medium: " + medium);
}

// Base movement magnitude M (mmu) per acceleration medium / sprint / ground
// surface, also from the generated table. simulate() does the forward/strafe 2D
// decomposition and sprint-jump 0.2 boost on top of this base.
float base_movement_magnitude(
    const std::string& acceleration_medium,
    const std::string& retention_medium,
    bool ground_sprint,
    bool air_prev_sprint) {
    namespace mc = movement_constants;
    if (acceleration_medium == "ground") {
        if (retention_medium == "flat_ground") {
            return static_cast<float>(ground_sprint ? mc::BASE_GROUND_FLAT_GROUND_SPRINT
                                                     : mc::BASE_GROUND_FLAT_GROUND_WALK);
        }
        if (retention_medium == "slime") {
            return static_cast<float>(ground_sprint ? mc::BASE_GROUND_SLIME_SPRINT
                                                     : mc::BASE_GROUND_SLIME_WALK);
        }
        if (retention_medium == "ice") {
            return static_cast<float>(ground_sprint ? mc::BASE_GROUND_ICE_SPRINT
                                                     : mc::BASE_GROUND_ICE_WALK);
        }
        throw std::runtime_error("unsupported ground retention medium: " + retention_medium);
    }
    if (acceleration_medium == "air") {
        return static_cast<float>(air_prev_sprint ? mc::BASE_AIR_SPRINT : mc::BASE_AIR_WALK);
    }
    if (acceleration_medium == "water") {
        return static_cast<float>(mc::BASE_WATER);
    }
    if (acceleration_medium == "lava") {
        return static_cast<float>(mc::BASE_LAVA);
    }
    throw std::runtime_error("unsupported movement slot acceleration medium: " + acceleration_medium);
}

// Effective ("actually sprinting") state for a slot: the sprint input as given.
// mothball move() applies the sprint boost from the raw sprinting arg and does
// NOT remove it for sneak/water/lava/wall (e.g. the sneaksprint command keeps
// sprint while sneaking). Whoever builds the plan (command parser or optimizer)
// decides the sprint input per tick; water/lava no-boost is handled by the
// acceleration branch (movement = 0.02), not by removing sprint here. Air sprint
// activation/removal is delayed one tick via the previous slot's effective sprint.
bool slot_effective_sprint(const MovementSlot& slot) {
    if (slot.kind == "init") {
        return false;
    }
    return slot.controls.sprint;
}

// ground_sprint is this slot's effective sprint (ground changes are immediate).
// air_prev_sprint is the previous slot's effective sprint (air sprint
// activation/removal is delayed one tick), matching mothball's prev_sprint.
SlotMovement derive_slot_movement(const MovementSlot& slot, bool ground_sprint, bool air_prev_sprint) {
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
    const float movement = base_movement_magnitude(
        slot.acceleration_medium, slot.retention_medium, ground_sprint, air_prev_sprint);

    // mmu carries the base movement magnitude M. simulate() does the forward/
    // strafe 2D decomposition and the separate sprint-jump 0.2 boost, mimicking
    // mothball's move(), so no-45/45/sneak are all handled the same way.
    return SlotMovement{
        static_cast<double>(retention_x),
        static_cast<double>(retention_z),
        static_cast<double>(movement)};
}

float mcsin_index(int index) {
    return static_cast<float>(
        std::sin(static_cast<double>(index & 65535) * 3.14159265358979323846 * 2.0 / 65536.0));
}

float mccos_index(int index) {
    return mcsin_index(index + 16384);
}

// Faithful port of mothball move() forward/strafe handling (player.py:146-178):
// scale forward/strafe by sneak (0.3) then 0.98, normalize by distance (clamped
// to >= 1), scale by the movement magnitude, and rotate by the facing yaw.
// movement is the base magnitude M; yaw_index encodes the facing.
void apply_movement_input(
    double& vx,
    double& vz,
    float movement,
    const Controls& controls,
    int yaw_index) {
    float forward = static_cast<float>(controls.forward);
    float strafe = static_cast<float>(controls.strafe);
    if (controls.sneak) {
        forward = static_cast<float>(static_cast<double>(forward) * 0.3);
        strafe = static_cast<float>(static_cast<double>(strafe) * 0.3);
    }
    forward = static_cast<float>(forward * 0.98F);
    strafe = static_cast<float>(strafe * 0.98F);
    float distance = static_cast<float>(strafe * strafe + forward * forward);
    if (distance < 0.0001F) {
        return;
    }
    distance = static_cast<float>(std::sqrt(static_cast<double>(distance)));
    if (distance < 1.0F) {
        distance = 1.0F;
    }
    distance = static_cast<float>(movement / distance);
    forward = static_cast<float>(forward * distance);
    strafe = static_cast<float>(strafe * distance);
    const float sin_yaw = mcsin_index(yaw_index);
    const float cos_yaw = mccos_index(yaw_index);
    // Round each product to float32 separately before combining (matching numpy
    // float32 arithmetic). Folding these into a fused multiply-add would compute
    // one product at extended precision and break the cancellation that makes a
    // symmetric 45 input produce exactly zero perpendicular drift.
    const float strafe_cos = static_cast<float>(strafe * cos_yaw);
    const float forward_sin = static_cast<float>(forward * sin_yaw);
    const float forward_cos = static_cast<float>(forward * cos_yaw);
    const float strafe_sin = static_cast<float>(strafe * sin_yaw);
    vx += static_cast<double>(strafe_cos - forward_sin);
    vz += static_cast<double>(forward_cos + strafe_sin);
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
        // Ground sprint is immediate (this slot); air sprint is delayed by one
        // tick (previous slot's effective sprint). The first slot has no prior.
        const bool ground_sprint = slot_effective_sprint(slot);
        const bool air_prev_sprint = index == 0
            ? false
            : slot_effective_sprint(input.movement_slots.at(static_cast<std::size_t>(index - 1)));
        const SlotMovement movement = derive_slot_movement(slot, ground_sprint, air_prev_sprint);
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
        const auto offset = static_cast<std::size_t>(index);
        // The input angle is the movement (travel/resultant) direction. The
        // facing (MC yaw, what the macro records and the repair tunes) differs
        // from the travel direction by the input's local angle: 0 for forward,
        // +/-45 deg for a forward+strafe diagonal. Derive the facing here.
        double facing_offset = 0.0;
        if (!input.movement_slots.empty()) {
            const MovementSlot& slot = input.movement_slots.at(offset);
            if (slot.kind != "init") {
                facing_offset = std::atan2(
                    static_cast<double>(slot.controls.strafe),
                    static_cast<double>(slot.controls.forward));
            }
        }
        const double yaw_radians =
            -input.movement_direction_radians.at(offset) + facing_offset;
        yaw_indices.push_back(mc_angle_index_from_radians(yaw_radians));
    }
    return yaw_indices;
}

std::vector<State> simulate(const ExactInput& input, const std::vector<int>& yaw_indices) {
    constexpr double inertia_threshold = 0.005;
    constexpr double ladder_clamp = 0.15;
    std::vector<State> states;
    State state = input.initial_state;
    states.push_back(state);

    bool prev_web = false;
    for (int index = 0; index < input.n; ++index) {
        const int slot = index + 1;
        const auto offset = static_cast<std::size_t>(index);
        const int yaw_index = yaw_indices.at(offset);
        const double movement_direction = yaw_index_to_movement_radians(yaw_index);
        const double imux = input.imux.at(offset);
        const double imuz = input.imuz.at(offset);
        const double mmu = input.mmu.at(offset);
        const MovementSlot* movement_slot = input.movement_slots.empty() ? nullptr : &input.movement_slots.at(offset);

        // Velocity contribution this tick. init seeds a raw speed along the
        // direction; movement slots add the sprint-jump boost then the
        // forward/strafe 2D movement (mothball order), all via the facing yaw.
        double dvx = 0.0;
        double dvz = 0.0;
        if (movement_slot != nullptr && movement_slot->kind == "init") {
            dvx = std::sin(movement_direction) * mmu;
            dvz = std::cos(movement_direction) * mmu;
        } else if (movement_slot != nullptr) {
            if (movement_slot->controls.jump && slot_effective_sprint(*movement_slot)) {
                dvx -= static_cast<double>(mcsin_index(yaw_index) * 0.2F);
                dvz += static_cast<double>(mccos_index(yaw_index) * 0.2F);
            }
            apply_movement_input(dvx, dvz, static_cast<float>(mmu), movement_slot->controls, yaw_index);
        }
        dvx = override_component(input.component_overrides, "mmux", slot, dvx);
        dvz = override_component(input.component_overrides, "mmuz", slot, dvz);

        const bool web = movement_slot != nullptr && movement_slot->web;
        const bool ladder = movement_slot != nullptr && movement_slot->ladder;

        // mothball: being in a web on the previous tick zeroes the carried
        // (post-drag) velocity at the start of this tick, before acceleration.
        if (prev_web) {
            state.vx = 0.0;
            state.vz = 0.0;
        }

        state.vx += dvx;
        state.vz += dvz;
        // Minecraft applies cobweb slowdown and ladder clamping to the motion
        // before the move (Entity.moveEntity), i.e. after acceleration.
        if (web) {
            state.vx /= 4.0;
            state.vz /= 4.0;
        }
        if (ladder) {
            state.vx = std::min(std::max(state.vx, -ladder_clamp), ladder_clamp);
            state.vz = std::min(std::max(state.vz, -ladder_clamp), ladder_clamp);
        }
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
        prev_web = web;
        state.tick = slot;
        states.push_back(state);
    }

    return states;
}

} // namespace wolframtas
