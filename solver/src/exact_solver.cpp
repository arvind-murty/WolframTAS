#include "wolframtas/exact_solver.hpp"

#include "wolframtas/exact_constraints.hpp"
#include "wolframtas/exact_movement.hpp"

#include <algorithm>
#include <cstddef>
#include <utility>
#include <vector>

namespace wolframtas {
namespace {

struct RepairMove {
    int index = 0;
    int delta = 0;
    double score = 0.0;
};

int wrap_angle_index(int index) {
    return index & 65535;
}

Evaluation evaluate_with_moves(
    const ExactInput& input,
    const std::vector<int>& current,
    const std::vector<RepairMove>& moves,
    std::vector<int>& candidate) {
    candidate = current;
    for (const RepairMove& move : moves) {
        candidate.at(static_cast<std::size_t>(move.index)) =
            wrap_angle_index(candidate.at(static_cast<std::size_t>(move.index)) + move.delta);
    }
    return evaluate_candidate(input, candidate);
}

} // namespace

RepairResult repair_angles(const ExactInput& input) {
    RepairResult result;
    result.yaw_indices = seed_yaw_indices(input);
    result.initial = evaluate_candidate(input, result.yaw_indices);
    result.final = result.initial;

    if (input.constraints.empty() && input.inertia_events.empty() && !input.objective.enabled) {
        return result;
    }
    if (result.final.feasible) {
        return result;
    }

    const SolverSettings& settings = input.solver_settings;
    for (int iteration = 0; iteration < settings.max_repair_iterations; ++iteration) {
        result.repair_iterations = iteration + 1;
        const double base_score = evaluation_score(result.final);
        std::vector<RepairMove> ranked_moves;

        const int max_delta = std::max(1, settings.max_index_delta_per_iteration);
        for (int index = 0; index < input.n; ++index) {
            for (int delta = 1; delta <= max_delta; ++delta) {
                if (result.candidate_evaluations >= settings.max_candidate_evaluations) {
                    break;
                }
                std::vector<int> candidate = result.yaw_indices;
                candidate.at(static_cast<std::size_t>(index)) =
                    wrap_angle_index(candidate.at(static_cast<std::size_t>(index)) - delta);
                const Evaluation negative_evaluation = evaluate_candidate(input, candidate);
                ++result.candidate_evaluations;
                const double negative_score = evaluation_score(negative_evaluation);
                if (negative_score < base_score) {
                    ranked_moves.push_back(RepairMove{index, -delta, negative_score});
                }

                if (result.candidate_evaluations >= settings.max_candidate_evaluations) {
                    break;
                }
                candidate = result.yaw_indices;
                candidate.at(static_cast<std::size_t>(index)) =
                    wrap_angle_index(candidate.at(static_cast<std::size_t>(index)) + delta);
                const Evaluation positive_evaluation = evaluate_candidate(input, candidate);
                ++result.candidate_evaluations;
                const double positive_score = evaluation_score(positive_evaluation);
                if (positive_score < base_score) {
                    ranked_moves.push_back(RepairMove{index, delta, positive_score});
                }
            }
        }

        if (ranked_moves.empty()) {
            break;
        }
        std::sort(ranked_moves.begin(), ranked_moves.end(), [](const RepairMove& left, const RepairMove& right) {
            return left.score < right.score;
        });
        const int top_count = std::min(settings.top_k_moves, static_cast<int>(ranked_moves.size()));

        std::vector<int> best_indices = result.yaw_indices;
        Evaluation best_evaluation = result.final;
        double best_score = base_score;

        auto try_moves = [&](const std::vector<RepairMove>& moves) {
            if (result.candidate_evaluations >= settings.max_candidate_evaluations) {
                return;
            }
            std::vector<int> candidate;
            const Evaluation evaluation = evaluate_with_moves(input, result.yaw_indices, moves, candidate);
            ++result.candidate_evaluations;
            const double score = evaluation_score(evaluation);
            if (score < best_score) {
                best_score = score;
                best_evaluation = evaluation;
                best_indices = std::move(candidate);
            }
        };

        for (int a = 0; a < top_count; ++a) {
            try_moves({ranked_moves.at(static_cast<std::size_t>(a))});
        }
        for (int a = 0; a < top_count; ++a) {
            for (int b = a + 1; b < top_count; ++b) {
                if (ranked_moves.at(static_cast<std::size_t>(a)).index
                    == ranked_moves.at(static_cast<std::size_t>(b)).index) {
                    continue;
                }
                try_moves({
                    ranked_moves.at(static_cast<std::size_t>(a)),
                    ranked_moves.at(static_cast<std::size_t>(b)),
                });
            }
        }
        for (int a = 0; a < top_count; ++a) {
            for (int b = a + 1; b < top_count; ++b) {
                for (int c = b + 1; c < top_count; ++c) {
                    const int ia = ranked_moves.at(static_cast<std::size_t>(a)).index;
                    const int ib = ranked_moves.at(static_cast<std::size_t>(b)).index;
                    const int ic = ranked_moves.at(static_cast<std::size_t>(c)).index;
                    if (ia == ib || ia == ic || ib == ic) {
                        continue;
                    }
                    try_moves({
                        ranked_moves.at(static_cast<std::size_t>(a)),
                        ranked_moves.at(static_cast<std::size_t>(b)),
                        ranked_moves.at(static_cast<std::size_t>(c)),
                    });
                }
            }
        }

        if (best_score >= base_score) {
            break;
        }
        result.yaw_indices = best_indices;
        result.final = best_evaluation;
        result.repaired = true;
        if (result.final.feasible || result.candidate_evaluations >= settings.max_candidate_evaluations) {
            break;
        }
    }

    return result;
}

} // namespace wolframtas
