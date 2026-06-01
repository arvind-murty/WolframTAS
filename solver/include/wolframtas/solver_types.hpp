#pragma once

#include <string>
#include <vector>

namespace wolframtas {

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
    std::string acceleration_input = "no45_forward";
    std::string retention_medium;
    bool wall_hit_x = false;
    bool wall_hit_z = false;
    bool web = false;
    bool ladder = false;
    double init_speed = 0.0;
    double init_imux = 0.0;
    double init_imuz = 0.0;
};

struct State {
    int tick = 0;
    double x = 0.0;
    double z = 0.0;
    double vx = 0.0;
    double vz = 0.0;
    double move_vx = 0.0;
    double move_vz = 0.0;
    double retained_vx = 0.0;
    double retained_vz = 0.0;
};

struct InertiaEvent {
    std::string id;
    std::string type;
    std::string axis;
    std::string direction;
    int slot = 0;
    double threshold = 0.005;
};

struct PositionConstraint {
    std::string id;
    int slot = 0;
    bool has_min_x = false;
    bool has_max_x = false;
    bool has_min_z = false;
    bool has_max_z = false;
    double min_x = 0.0;
    double max_x = 0.0;
    double min_z = 0.0;
    double max_z = 0.0;
    double exact_tolerance = 0.001;
};

struct ExactObjective {
    bool enabled = false;
    std::string axis = "z";
    int slot = 0;
    bool target_value_set = false;
    double target_value = 0.0;
    double tolerance = 0.001;
};

struct SolverSettings {
    int max_repair_iterations = 8;
    int max_candidate_evaluations = 2000;
    int top_k_moves = 8;
    int max_index_delta_per_iteration = 1;
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
    std::vector<InertiaEvent> inertia_events;
    std::vector<PositionConstraint> constraints;
    ExactObjective objective;
    SolverSettings solver_settings;
};

struct Evaluation {
    std::vector<State> states;
    double residual_norm = 0.0;
    double objective_value = 0.0;
    double objective_deviation = 0.0;
    double objective_residual = 0.0;
    std::string worst_constraint_id;
    double worst_constraint_residual = 0.0;
    bool feasible = true;
};

struct RepairResult {
    std::vector<int> yaw_indices;
    Evaluation initial;
    Evaluation final;
    int candidate_evaluations = 0;
    int repair_iterations = 0;
    bool repaired = false;
};

} // namespace wolframtas
