cmake_minimum_required(VERSION 3.16)
project(wolframtas_solver LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(wolframtas_solver
    src/main.cpp
)

target_include_directories(wolframtas_solver PRIVATE include)

add_executable(angle_table_smoke
    tests/angle_table_smoke.cpp
)

target_include_directories(angle_table_smoke PRIVATE include)

enable_testing()
add_test(NAME angle_table_smoke COMMAND angle_table_smoke)
add_test(
    NAME exact_solver_fixture
    COMMAND /bin/sh -c "$<TARGET_FILE:wolframtas_solver> < ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/exact_solver_input.json"
)
add_test(
    NAME exact_solver_flat_sprintjump
    COMMAND /bin/sh -c "$<TARGET_FILE:wolframtas_solver> < ${CMAKE_CURRENT_SOURCE_DIR}/../examples/simple_jump/flat_sprintjump_exact_solver_input.json | grep -q '\"z\": \"2.6234314852435587\".*\"z\": \"0.2269176215282418\"'"
)
