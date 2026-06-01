cmake_minimum_required(VERSION 3.16)
project(wolframtas_solver LANGUAGES CXX)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

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
add_test(
    NAME exact_solver_flat_sprintjump
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/flat_sprintjump_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        --expect states_exact[12].position.z=2.6234314852435587
        --expect states_exact[12].velocity.z=0.24936001647089573
        --expect diagnostics.final_residual_norm=0
        --expect diagnostics.objective_deviation=0
        --expect-macro-line W,A,S,D,P,N,J,YAW,PITCH,L,R,COUNT
        --expect-macro-line true,false,false,false,true,false,true,0,0,0,0,1
)
add_test(
    NAME exact_solver_flat_sprintjump_45
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/assert_solver_fixture.py
        --solver $<TARGET_FILE:wolframtas_solver>
        --input ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/flat_sprintjump_45_exact_solver_input.json
        --validate-exact-solution-schema
        --expect status=solved
        --expect states_exact[12].position.z=2.645539114938402
        --expect states_exact[12].velocity.z=0.2528878364238645
        --expect diagnostics.final_residual_norm=0
        --expect diagnostics.objective_deviation=0
)
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
