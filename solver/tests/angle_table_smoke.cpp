#include "wolftas/angle_table.hpp"

#include <cassert>

int main() {
    assert(wolftas::degrees_to_index(0.0) == 0);
    assert(wolftas::degrees_to_index(360.0) == 0);
    assert(wolftas::degrees_to_index(-360.0) == 0);
    assert(wolftas::degrees_to_index(180.0) == 8192);
    assert(wolftas::snap_degrees(0.0) == 0.0);
    return 0;
}
