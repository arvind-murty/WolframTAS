cmake_minimum_required(VERSION 3.16)
project(wolftas_solver LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(wolftas_solver
    src/main.cpp
)

target_include_directories(wolftas_solver PRIVATE include)

add_executable(angle_table_smoke
    tests/angle_table_smoke.cpp
)

target_include_directories(angle_table_smoke PRIVATE include)

enable_testing()
add_test(NAME angle_table_smoke COMMAND angle_table_smoke)
