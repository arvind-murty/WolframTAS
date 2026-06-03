cmake_minimum_required(VERSION 3.16)
project(wolframtas_solver LANGUAGES CXX)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# The solver must reproduce numpy float32 arithmetic bit-exactly (mothball
# reference). numpy never fuses multiply-add, so disable FP contraction; a fused
# multiply-add computes one product at extended precision and breaks exact
# cancellation (e.g. symmetric 45 inputs would leave a ~1e-9 perpendicular drift).
add_compile_options(-ffp-contract=off)

add_library(wolframtas_solver_core
    src/exact_constraints.cpp
    src/exact_input.cpp
    src/exact_movement.cpp
    src/exact_solver.cpp
    src/solution_writer.cpp
)

target_include_directories(wolframtas_solver_core PUBLIC include)

add_executable(wolframtas_solver
    src/main.cpp
)

target_link_libraries(wolframtas_solver PRIVATE wolframtas_solver_core)

add_executable(angle_table_smoke
    tests/angle_table_smoke.cpp
)

target_include_directories(angle_table_smoke PRIVATE include)

add_executable(exact_movement_tests
    tests/exact_movement_tests.cpp
)

target_link_libraries(exact_movement_tests PRIVATE wolframtas_solver_core)

add_executable(exact_constraints_tests
    tests/exact_constraints_tests.cpp
)

target_link_libraries(exact_constraints_tests PRIVATE wolframtas_solver_core)

enable_testing()
add_test(NAME angle_table_smoke COMMAND angle_table_smoke)
add_test(NAME exact_movement_tests COMMAND exact_movement_tests)
add_test(NAME exact_constraints_tests COMMAND exact_constraints_tests)
# ALL movement/medium physics (flat sprint-jump, 45, water, lava, slime, ice,
# ladder, web, sneak, sprint delay) is validated bit-exact against the mothball
# reference simulator by parsing mothball command strings and comparing x/z/vx/vz
# to mothball — the source of truth, no hand-authored expected values; see
# e2e/test_command_parser.py.
#
# The fixtures below test solver behaviour mothball commands cannot express
# (angle repair, constraint/objective failure, wall-axis cancellation, the
# seeded-velocity inertia threshold). They assert ONLY behavioural/structural
# outcomes — status, which constraint failed, repaired angle indices, a residual
# of exactly 0, or an axis a wall/threshold zeroes to exactly 0 — never a
# self-generated physics magnitude.
add_test(
    NAME exact_solver_repairs_angle_index
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/repair_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        --expect diagnostics.changed_angle_indices[0].slot=2
        --expect diagnostics.changed_angle_indices[0].delta=-1
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_uses_configured_index_delta
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/repair_two_index_delta_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        --expect diagnostics.changed_angle_indices[0].slot=2
        --expect diagnostics.changed_angle_indices[0].to=65534
        --expect diagnostics.changed_angle_indices[0].delta=-2
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_reports_impossible_constraint
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/impossible_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=failed
        --expect diagnostics.worst_constraint_id=impossible_x
)
add_test(
    NAME exact_solver_enforces_objective_tolerance
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/objective_fail_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=failed
)
add_test(
    NAME exact_solver_inertia_hit
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/inertia_hit_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        # The inertia hit drops the x velocity below the 0.005 threshold, so it
        # is zeroed; pure-x motion keeps z at exactly 0. Structural, not a magnitude.
        --expect states_exact[3].velocity.x=0
        --expect states_exact[3].position.z=0
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_inertia_avoid
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/inertia_avoid_exact_solver_input.json
        --validate-exact-solution-schema
        # Inertia avoid: the velocity stays above threshold, so the avoid
        # constraint is satisfied and the solve succeeds with zero residual.
        --expect status=solved
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_wall_hit_x
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/wall_hit_x_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        # The X wall cancels the x velocity to exactly 0 on the hit tick.
        # Structural (the blocked axis is zeroed), not a self-generated magnitude.
        --expect states_exact[3].velocity.x=0
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_wall_sprint_cancel
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/wall_sprint_cancel_exact_solver_input.json
        --validate-exact-solution-schema
        # Sprint cancel at an air wall tick: the scenario solves to zero residual.
        # The sprint-delay mechanics themselves are validated bit-exact against
        # mothball (sprintair / sns45 / sj45 ... in e2e/test_command_parser.py).
        --expect status=solved
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_wall_collision_x
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/wall_collision_x_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        # Threshold collision on X: crossing clamps X and zeroes retained X velocity.
        --expect states_exact[1].retained_velocity.x=0
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_wall_collision_z
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/wall_collision_z_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        # Threshold collision on Z: crossing clamps Z and zeroes retained Z velocity.
        --expect states_exact[1].retained_velocity.z=0
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_wall_collision_z_no_cross
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/wall_collision_z_no_cross_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        # No crossing case: the position remains the moved value (0.2), so no
        # wall clamp to z=0.25 occurred.
        --expect states_exact[1].position.z=0.2
        --expect diagnostics.final_residual_norm=0
)
