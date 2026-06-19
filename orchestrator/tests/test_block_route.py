from __future__ import annotations

import json
import math
from pathlib import Path

from wolframtas_orchestrator.block_route import block_route_to_candidate_bundle, block_route_to_exact_template
from wolframtas_orchestrator.cli import main
from wolframtas_orchestrator.python_solver import solve
from wolframtas_orchestrator.vertical_model import jump_air_ticks


def test_jump_air_ticks_from_mothball_vertical_model() -> None:
    assert jump_air_ticks(65.0, 65.0) == 11
    assert jump_air_ticks(65.0, 66.0) == 8
    assert jump_air_ticks(65.0, 64.0) == 13


def test_block_route_generates_run_and_landing_constraints() -> None:
    template = block_route_to_exact_template(
        {
            "version": 1,
            "name": "two_block_route",
            "blocks": [
                {"id": "start", "x": 10, "y": 64, "z": 20, "width": 1, "length": 1, "run_ticks": 2},
                {"id": "target", "x": 10, "y": 64, "z": 23, "width": 2, "length": 1, "run_ticks": 0},
            ],
        }
    )

    assert template["n"] == 15
    slots = template["movement_plan"]["slots"]
    assert slots[0]["kind"] == "init"
    assert slots[1]["controls"] == {"forward": 1, "strafe": 0, "jump": False, "sneak": False, "sprint": True}
    assert slots[2]["controls"]["jump"] is False
    assert slots[3]["controls"]["jump"] is True
    assert all(slot["controls"]["strafe"] == 1 for slot in slots[4:])

    constraints = {constraint["id"]: constraint for constraint in template["constraints"]}
    assert set(constraints) == {
        "run_start_tick_2",
        "run_start_tick_3",
        "land_target_tick_15",
    }
    assert constraints["run_start_tick_2"]["slot"] == 2
    assert constraints["run_start_tick_3"]["slot"] == 3
    assert constraints["land_target_tick_15"]["slot"] == 15
    assert constraints["land_target_tick_15"]["min_x"] == -0.3
    assert constraints["land_target_tick_15"]["max_x"] == 2.3
    assert constraints["land_target_tick_15"]["min_z"] == 2.7
    assert constraints["land_target_tick_15"]["max_z"] == 4.3


def test_block_route_accepts_explicit_landing_blocks_alias() -> None:
    template = block_route_to_exact_template(
        {
            "version": 1,
            "name": "landing_alias",
            "landing_blocks": [
                {"kind": "landing", "id": "start", "x": 0, "y": 64, "z": 0},
                {"kind": "landing", "id": "finish", "x": 0, "y": 64, "z": 3},
            ],
        }
    )

    assert template["annotations"][0]["landing_blocks"][0]["kind"] == "landing"
    assert template["constraints"][0]["id"] == "land_finish_tick_13"


def test_block_route_uses_departure_block_run_ticks_across_segments() -> None:
    template = block_route_to_exact_template(
        {
            "version": 1,
            "blocks": [
                {"id": "a", "x": 0, "y": 64, "z": 0, "run_ticks": 0},
                {"id": "b", "x": 0, "y": 65, "z": 3, "run_ticks": 1},
                {"id": "c", "x": 0, "y": 64, "z": 6, "run_ticks": 0},
            ],
        }
    )

    constraints = {constraint["id"]: constraint for constraint in template["constraints"]}
    assert constraints["land_b_tick_10"]["slot"] == 10
    assert constraints["run_b_tick_11"]["slot"] == 11
    assert constraints["land_c_tick_25"]["slot"] == 25
    assert template["n"] == 25


def test_block_route_rejects_final_run_ticks() -> None:
    try:
        block_route_to_exact_template(
            {
                "version": 1,
                "blocks": [
                    {"x": 0, "y": 64, "z": 0, "run_ticks": 0},
                    {"x": 0, "y": 64, "z": 3, "run_ticks": 1},
                ],
            }
        )
    except ValueError as exc:
        assert "final block run_ticks" in str(exc)
    else:
        raise AssertionError("expected final run_ticks rejection")


def test_block_route_avoid_blocks_generate_candidate_bundle() -> None:
    bundle = block_route_to_candidate_bundle(
        {
            "version": 1,
            "name": "avoid_route",
            "landing_blocks": [
                {"id": "start", "x": 0, "y": 64, "z": 0},
                {"id": "finish", "x": 0, "y": 64, "z": 6},
            ],
            "avoid_blocks": [
                {
                    "kind": "avoid",
                    "id": "post",
                    "x": 0,
                    "y": 65,
                    "z": 3,
                    "between": ["start", "finish"],
                    "corner_hints": ["north_west"],
                    "transition_tick_window": [3, 8],
                }
            ],
        }
    )

    assert bundle["kind"] == "block_route_candidate_bundle"
    assert bundle["candidate_count"] == 9
    choices = [candidate["avoid_choices"][0] for candidate in bundle["candidates"]]
    assert all(choice["active_slots"] == [3, 4] for choice in choices)
    assert choices[0]["schedule"]["kind"] == "route_transition"
    assert [phase["side"] for phase in choices[0]["schedule"]["phases"]] == ["north", "south"]

    first_constraints = {
        constraint["id"]: constraint
        for constraint in bundle["candidates"][0]["exact_template"]["constraints"]
        if constraint["id"].startswith("avoid_")
    }
    assert first_constraints["avoid_post_route_transition_p1_north_tick_3"]["max_z"] == 2.7
    assert first_constraints["avoid_post_route_transition_p2_south_tick_4"]["min_z"] == 4.3


def test_block_route_demo_has_feasible_avoid_candidate() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    route = json.loads((repo_root / "examples/block_route_demo/block_route.json").read_text(encoding="utf-8"))
    bundle = block_route_to_candidate_bundle(route)
    candidate = next(
        item for item in bundle["candidates"]
        if item["avoid_choices"][0]["schedule"].get("transition_after_slot") == 14
        and [phase["side"] for phase in item["avoid_choices"][0]["schedule"]["phases"]] == ["north", "south"]
    )
    exact_template = candidate["exact_template"]
    directions = []
    for slot in range(1, exact_template["n"] + 1):
        radians = 0.0
        if 12 <= slot <= 14:
            radians = math.radians(-32)
        elif 15 <= slot <= exact_template["n"]:
            radians = math.radians(76)
        directions.append({"slot": slot, "radians": radians})
    exact_template["optimal_solution"] = {
        "status": "seed",
        "objective_value": 5.958334226758805,
        "movement_directions": directions,
    }
    exact_template["exact_objective"]["target_value"] = 5.958334226758805
    exact_template["exact_objective"]["solution_tolerance"] = 1.0

    solution = solve(exact_template)

    assert solution["status"] == "solved"
    assert solution["diagnostics"]["final_residual_norm"] == "0.0"


def test_block_route_rejects_avoid_blocks_between_nonconsecutive_landings() -> None:
    try:
        block_route_to_candidate_bundle(
            {
                "version": 1,
                "landing_blocks": [
                    {"id": "a", "x": 0, "y": 64, "z": 0},
                    {"id": "b", "x": 0, "y": 64, "z": 3},
                    {"id": "c", "x": 0, "y": 64, "z": 6},
                ],
                "avoid_blocks": [
                    {"id": "bad", "x": 0, "y": 65, "z": 2, "between": ["a", "c"]},
                ],
            }
        )
    except ValueError as exc:
        assert "consecutive landing blocks" in str(exc)
    else:
        raise AssertionError("expected nonconsecutive avoid rejection")


def test_build_block_route_cli_writes_template(tmp_path: Path) -> None:
    route = tmp_path / "route.json"
    out = tmp_path / "template.json"
    route.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "cli_route",
                "blocks": [
                    {"x": 0, "y": 64, "z": 0},
                    {"x": 0, "y": 64, "z": 3},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert main(["build-block-route", str(route), "--out", str(out)]) == 0
    template = json.loads(out.read_text(encoding="utf-8"))
    assert template["name"] == "cli_route"
    assert template["n"] == 13
    assert template["constraints"][0]["id"] == "land_b1_tick_13"


def test_build_block_route_cli_writes_candidate_bundle_for_avoid_blocks(tmp_path: Path) -> None:
    route = tmp_path / "route.json"
    out = tmp_path / "candidates.json"
    route.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "cli_avoid_route",
                "landing_blocks": [
                    {"id": "start", "x": 0, "y": 64, "z": 0},
                    {"id": "finish", "x": 0, "y": 64, "z": 6},
                ],
                "avoid_blocks": [
                    {
                        "id": "post",
                        "x": 0,
                        "y": 65,
                        "z": 3,
                        "between": ["start", "finish"],
                        "corner_hints": ["north_west"],
                    }
                ],
                "candidate_selection": {"max_generated_candidates": 2},
            }
        ),
        encoding="utf-8",
    )

    assert main(["build-block-route", str(route), "--out", str(out)]) == 0
    bundle = json.loads(out.read_text(encoding="utf-8"))
    assert bundle["kind"] == "block_route_candidate_bundle"
    assert bundle["candidates"][0]["exact_template"]["name"].startswith("cli_avoid_route_candidate_")


def test_score_block_route_cli_ranks_and_selects_candidates(tmp_path: Path) -> None:
    route = tmp_path / "route.json"
    scored_out = tmp_path / "scored.json"
    selected_out = tmp_path / "selected.json"
    fake_wolframscript = tmp_path / "fake_wolframscript"
    route.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "score_route",
                "landing_blocks": [
                    {"id": "start", "x": 0, "y": 64, "z": 0},
                    {"id": "finish", "x": 0, "y": 64, "z": 6},
                ],
                "avoid_blocks": [
                    {
                        "id": "post",
                        "x": 0,
                        "y": 65,
                        "z": 3,
                        "between": ["start", "finish"],
                        "corner_hints": ["north_west"],
                    }
                ],
                "candidate_selection": {"max_generated_candidates": 2},
            }
        ),
        encoding="utf-8",
    )
    fake_wolframscript.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "problem = json.load(open(sys.argv[3]))\n"
        "assert problem['optimizer']['method'] == 'NelderMead'\n"
        "assert problem['optimizer']['accuracy_goal'] == 3\n"
        "assert problem['optimizer']['precision_goal'] == 3\n"
        "assert problem['optimizer']['max_iterations'] == 300\n"
        "assert any('+ 0.03' in c['expression'] or '- 0.03' in c['expression'] for c in problem['constraints'])\n"
        "objective = 10.0 if problem['name'].endswith('candidate_002') else 9.99\n"
        "print(json.dumps({\n"
        "  'version': 1,\n"
        "  'status': 'optimal',\n"
        "  'objective_value': objective,\n"
        "  'movement_directions': [{'slot': i + 1, 'radians': 0.0} for i in range(problem['n'])]\n"
        "}))\n",
        encoding="utf-8",
    )
    fake_wolframscript.chmod(0o755)

    assert main([
        "score-block-route",
        str(route),
        "--out",
        str(scored_out),
        "--selected-out",
        str(selected_out),
        "--wolframscript",
        str(fake_wolframscript),
        "--max-precise-candidates",
        "1",
        "--objective-margin",
        "0.005",
    ]) == 0

    scored = json.loads(scored_out.read_text(encoding="utf-8"))
    selected = json.loads(selected_out.read_text(encoding="utf-8"))
    assert scored["kind"] == "scored_block_route_candidate_bundle"
    assert [candidate["id"] for candidate in scored["candidates"]] == ["candidate_002", "candidate_001"]
    assert scored["selection"]["selected_candidate_ids"] == ["candidate_002"]
    assert selected["candidate_count"] == 1
    assert selected["candidates"][0]["id"] == "candidate_002"


def test_solve_block_route_candidates_cli_runs_selected_precise_candidates(tmp_path: Path) -> None:
    selected = tmp_path / "selected.json"
    output = tmp_path / "precise.json"
    fake_wolframscript = tmp_path / "fake_wolframscript"
    selected.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "selected_block_route_candidates",
                "name": "precise_route",
                "candidate_count": 2,
                "candidates": [
                    {"id": "candidate_001", "avoid_choices": [], "exact_template": _tiny_exact_template("candidate_001", 0.1)},
                    {"id": "candidate_002", "avoid_choices": [], "exact_template": _tiny_exact_template("candidate_002", 0.2)},
                ],
            }
        ),
        encoding="utf-8",
    )
    fake_wolframscript.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "problem = json.load(open(sys.argv[3]))\n"
        "objective = 0.2 if problem['name'] == 'candidate_002' else 0.1\n"
        "print(json.dumps({\n"
        "  'version': 1,\n"
        "  'status': 'optimal',\n"
        "  'objective_value': objective,\n"
        "  'movement_directions': [{'slot': i + 1, 'radians': 0.0} for i in range(problem['n'])]\n"
        "}))\n",
        encoding="utf-8",
    )
    fake_wolframscript.chmod(0o755)

    assert main([
        "solve-block-route-candidates",
        str(selected),
        "--out",
        str(output),
        "--wolframscript",
        str(fake_wolframscript),
        "--default-relaxed-tolerance",
        "0.0",
    ]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["kind"] == "precise_block_route_candidate_results"
    assert payload["status"] == "solved"
    assert payload["candidate_count"] == 2
    assert payload["completed_candidate_count"] == 2
    assert payload["error_candidate_count"] == 0
    assert payload["best_candidate_id"] == "candidate_002"
    assert [result["exact_solution"]["status"] for result in payload["results"]] == ["solved", "solved"]


def test_solve_block_route_candidates_cli_continues_after_candidate_error(tmp_path: Path) -> None:
    selected = tmp_path / "selected.json"
    output = tmp_path / "precise.json"
    fake_wolframscript = tmp_path / "fake_wolframscript"
    selected.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "selected_block_route_candidates",
                "name": "precise_route",
                "candidate_count": 2,
                "candidates": [
                    {"id": "candidate_001", "avoid_choices": [], "exact_template": _tiny_exact_template("candidate_001", 0.1)},
                    {"id": "candidate_002", "avoid_choices": [], "exact_template": _tiny_exact_template("candidate_002", 0.2)},
                ],
            }
        ),
        encoding="utf-8",
    )
    fake_wolframscript.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "problem = json.load(open(sys.argv[3]))\n"
        "if problem['name'] == 'candidate_001':\n"
        "    print(json.dumps({'version': 1, 'status': 'error', 'diagnostics': {'message': 'bad candidate'}}))\n"
        "    sys.exit(1)\n"
        "print(json.dumps({\n"
        "  'version': 1,\n"
        "  'status': 'optimal',\n"
        "  'objective_value': 0.2,\n"
        "  'movement_directions': [{'slot': i + 1, 'radians': 0.0} for i in range(problem['n'])]\n"
        "}))\n",
        encoding="utf-8",
    )
    fake_wolframscript.chmod(0o755)

    assert main([
        "solve-block-route-candidates",
        str(selected),
        "--out",
        str(output),
        "--wolframscript",
        str(fake_wolframscript),
        "--default-relaxed-tolerance",
        "0.0",
    ]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "solved"
    assert payload["best_candidate_id"] == "candidate_002"
    assert payload["completed_candidate_count"] == 1
    assert payload["error_candidate_count"] == 1
    assert payload["results"][0]["status"] == "error"
    assert "bad candidate" in payload["results"][0]["error"]
    assert payload["results"][1]["status"] == "completed"


def test_solve_block_route_candidates_falls_back_to_coarse_solution(tmp_path: Path) -> None:
    selected = tmp_path / "selected.json"
    output = tmp_path / "precise.json"
    fake_wolframscript = tmp_path / "fake_wolframscript"
    template = _tiny_exact_template("candidate_001", 0.2)
    selected.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "selected_block_route_candidates",
                "name": "coarse_fallback_route",
                "candidate_count": 1,
                "candidates": [
                    {
                        "id": "candidate_001",
                        "avoid_choices": [],
                        "coarse_score": {"objective_value": 0.2},
                        "coarse_solution": {
                            "version": 1,
                            "status": "optimal",
                            "objective_value": 0.2,
                            "movement_directions": [{"slot": 1, "radians": 0.0}],
                        },
                        "exact_template": template,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    fake_wolframscript.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "_problem = json.load(open(sys.argv[3]))\n"
        "print(json.dumps({'version': 1, 'status': 'error', 'diagnostics': {'message': 'strict failed'}}))\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    fake_wolframscript.chmod(0o755)

    assert main([
        "solve-block-route-candidates",
        str(selected),
        "--out",
        str(output),
        "--wolframscript",
        str(fake_wolframscript),
        "--default-relaxed-tolerance",
        "0.0",
    ]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "solved"
    assert payload["completed_candidate_count"] == 1
    assert payload["error_candidate_count"] == 0
    assert payload["best_candidate_id"] == "candidate_001"
    assert payload["results"][0]["status"] == "completed_from_coarse"
    assert payload["results"][0]["exact_solution"]["status"] == "solved"


def test_solve_block_route_cli_runs_full_one_shot_flow(tmp_path: Path) -> None:
    route = tmp_path / "route.json"
    output = tmp_path / "result.json"
    build_out = tmp_path / "built.json"
    score_out = tmp_path / "scored.json"
    selected_out = tmp_path / "selected.json"
    fake_wolframscript = tmp_path / "fake_wolframscript"
    route.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "one_shot_route",
                "landing_blocks": [
                    {"id": "start", "x": 0, "y": 64, "z": 0},
                    {"id": "finish", "x": 0, "y": 64, "z": 6},
                ],
                "avoid_blocks": [
                    {
                        "id": "post",
                        "x": 0,
                        "y": 65,
                        "z": 3,
                        "between": ["start", "finish"],
                        "corner_hints": ["north_west"],
                    }
                ],
                "candidate_selection": {
                    "max_generated_candidates": 2,
                    "max_precise_candidates": 1,
                    "objective_margin": 0.0,
                    "coarse_tolerance": 0.04,
                    "coarse_optimizer": {
                        "method": "DifferentialEvolution",
                        "accuracy_goal": 2,
                        "precision_goal": 2,
                        "max_iterations": 25,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    fake_wolframscript.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "problem = json.load(open(sys.argv[3]))\n"
        "if problem['optimizer'].get('method') == 'DifferentialEvolution':\n"
        "    assert problem['optimizer']['accuracy_goal'] == 2\n"
        "    assert problem['optimizer']['precision_goal'] == 2\n"
        "    assert problem['optimizer']['max_iterations'] == 25\n"
        "    assert any('+ 0.04' in c['expression'] or '- 0.04' in c['expression'] for c in problem['constraints'])\n"
        "objective = 10.0 if problem['name'].endswith('candidate_002') else 9.0\n"
        "print(json.dumps({\n"
        "  'version': 1,\n"
        "  'status': 'optimal',\n"
        "  'objective_value': objective,\n"
        "  'movement_directions': [{'slot': i + 1, 'radians': 0.0} for i in range(problem['n'])]\n"
        "}))\n",
        encoding="utf-8",
    )
    fake_wolframscript.chmod(0o755)

    assert main([
        "solve-block-route",
        str(route),
        "--out",
        str(output),
        "--build-out",
        str(build_out),
        "--score-out",
        str(score_out),
        "--selected-out",
        str(selected_out),
        "--wolframscript",
        str(fake_wolframscript),
        "--default-relaxed-tolerance",
        "0.0",
    ]) == 0

    result = json.loads(output.read_text(encoding="utf-8"))
    scored = json.loads(score_out.read_text(encoding="utf-8"))
    selected = json.loads(selected_out.read_text(encoding="utf-8"))
    assert build_out.exists()
    assert scored["selection"]["selected_candidate_ids"] == ["candidate_002"]
    assert selected["candidate_count"] == 1
    assert result["status"] == "solved"
    assert result["best_candidate_id"] == "candidate_002"
    assert result["candidate_count"] == 1


def _tiny_exact_template(name: str, init_speed: float) -> dict:
    return {
        "version": 1,
        "name": name,
        "slot_indexing": "1_based",
        "n": 1,
        "angle_domain": {"table_size": 65536},
        "initial_state": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "yaw": 0.0,
            "pitch": 0.0,
            "on_ground": True,
        },
        "movement_plan": {
            "version": 1,
            "slot_indexing": "1_based",
            "slots": [{"slot": 1, "kind": "init", "speed": init_speed, "imux": 0.91, "imuz": 0.91}],
        },
        "constraints": [],
        "exact_objective": {
            "type": "position",
            "axis": "z",
            "slot": 1,
            "sense": "maximize",
            "solution_tolerance": 0.001,
        },
    }
