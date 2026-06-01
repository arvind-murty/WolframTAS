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
# Movement/medium scenarios (flat sprint-jump, 45, water, lava, slime, ice,
# ladder, web, sneak, sprint delay) are validated by parsing mothball command
# strings and comparing the solver to the mothball simulator; see
# e2e/test_command_parser.py (no hand-authored expected values). The fast C++
# unit test (exact_movement_tests) still pins the locked sprint-jump outputs.
# The fixtures below test solver behaviour mothball commands can't express:
# angle repair, constraint/objective failure, wall-axis cancellation, and the
# seeded-velocity inertia threshold.
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
        --expect diagnostics.objective_deviation=0.32739998400211334
)
add_test(
    NAME exact_solver_inertia_hit
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/inertia_hit_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        --expect states_exact[2].position.x=0.01050500014424324
        --expect states_exact[2].velocity.x=0.00500500014424324
        --expect states_exact[3].velocity.x=0
        --expect states_exact[3].position.x=0.01050500014424324
        --expect states_exact[3].position.z=0
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_inertia_avoid
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/inertia_avoid_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        --expect states_exact[4].position.z=0.4302313432562946
        --expect states_exact[4].velocity.z=0.1807233625357752
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_wall_hit_x
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/wall_hit_x_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        --expect states_exact[3].position.x=0.3820000052452088
        --expect states_exact[3].velocity.x=0
        --expect states_exact[3].position.z=0.5476200147914888
        --expect states_exact[3].velocity.z=0.16562000954628006
        --expect diagnostics.final_residual_norm=0
)
add_test(
    NAME exact_solver_wall_sprint_cancel
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/wall_sprint_cancel_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        --expect states_exact[4].velocity.z=0.0845367786639481
        --expect states_exact[4].position.z=0.21235033687733879
        --expect states_exact[5].position.z=0.30887880791105493
        --expect states_exact[6].position.z=0.4221997175228469
        --expect diagnostics.final_residual_norm=0
)
