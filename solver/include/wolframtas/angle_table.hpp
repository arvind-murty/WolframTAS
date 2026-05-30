#pragma once

#include <cmath>
#include <cstdint>

namespace wolframtas {

constexpr std::int32_t kAngleTableSize = 16384;

inline std::int32_t degrees_to_index(double degrees) {
    const double wrapped = std::fmod(std::fmod(degrees, 360.0) + 360.0, 360.0);
    const auto index = static_cast<std::int32_t>(std::llround(wrapped / 360.0 * kAngleTableSize));
    return index & (kAngleTableSize - 1);
}

inline double index_to_degrees(std::int32_t index) {
    return static_cast<double>(index & (kAngleTableSize - 1)) * 360.0 / kAngleTableSize;
}

inline double snap_degrees(double degrees) {
    return index_to_degrees(degrees_to_index(degrees));
}

} // namespace wolframtas
