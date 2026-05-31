#include "wolframtas/angle_table.hpp"

#include <cassert>

int main() {
    assert(wolframtas::degrees_to_index(0.0) == 0);
    assert(wolframtas::degrees_to_index(360.0) == 0);
    assert(wolframtas::degrees_to_index(-360.0) == 0);
    assert(wolframtas::degrees_to_index(180.0) == 32768);
    assert(wolframtas::snap_degrees(0.0) == 0.0);
    return 0;
}
