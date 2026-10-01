import json
from collections import Counter

import pytest

from ai.execution.contract import contract_hash, validate_contract
from zyra_cmd.synthetic_tasks import (
    MAX_CATALOG_TASKS,
    SyntheticTaskFeeder,
    catalog,
    generate_synthetic_tasks,
    main,
    randomized_task_specs,
)


def test_catalog_contains_24_reviewed_types_across_all_reward_categories():
    entries = catalog()
    assert len(entries) == 24
    assert {entry["reward_category"] for entry in entries} == {
        "light", "medium", "heavy", "very_heavy"
    }
    assert Counter(entry["reward_category"] for entry in entries) == {
        "light": 6, "medium": 6, "heavy": 6, "very_heavy": 6
    }
    assert len({entry["template_id"] for entry in entries}) == 24


def test_synthetic_preview_selection_is_reproducible_and_not_submitted():
    first = generate_synthetic_tasks(seed=2718, count=MAX_CATALOG_TASKS)
    second = generate_synthetic_tasks(seed=2718, count=MAX_CATALOG_TASKS)

    assert first == second
    assert len({task["preview_id"] for task in first}) == MAX_CATALOG_TASKS
    assert all(task["status"] == "preview_only_not_submitted" for task in first)
    assert all(task["reward_mode"] == "chain-task-category" for task in first)
    assert all(task["origin"] == "synthetic" for task in first)


def test_each_synthetic_acceptance_contract_is_executable():
    for task in generate_synthetic_tasks(seed=17, count=MAX_CATALOG_TASKS):
        acceptance = validate_contract(task["acceptance"])
        assert task["acceptance_hash"] == contract_hash(acceptance)
        assert acceptance["criteria"]
        assert all("check" in criterion for criterion in acceptance["criteria"])
        assert task["runtime_profile"] == acceptance["profile"]


def test_live_sequence_has_randomized_order_and_covers_each_category():
    specs = list(randomized_task_specs(seed=22, count=12))
    assert len(specs) == 12
    assert len({spec["template_id"] for spec in specs}) == 12
    assert all(spec["status"] == "preview_only_not_submitted" for spec in specs)
    for start in range(0, 12, 4):
        assert {spec["reward_category"] for spec in specs[start:start + 4]} == {
            "light", "medium", "heavy", "very_heavy"
        }


def test_live_feeder_submits_bounded_tasks_and_calls_status_callback():
    submitted = []
    events = []
    feeder = SyntheticTaskFeeder(
        lambda spec: submitted.append(spec) or {"task_id": f"task-{len(submitted)}"},
        count=4,
        min_interval=0,
        max_interval=0,
        seed=8,
        on_event=events.append,
    ).start()
    feeder._thread.join(timeout=3)

    assert not feeder.running
    assert feeder.submitted == 4
    assert len(submitted) == 4
    assert all(spec["status"] == "preview_only_not_submitted" for spec in submitted)
    assert any("task-4" in event for event in events)


def test_synthetic_generator_rejects_invalid_category_and_count():
    with pytest.raises(ValueError, match="Unknown synthetic task category"):
        generate_synthetic_tasks(seed=1, category="unknown")
    with pytest.raises(ValueError, match="count must be between"):
        generate_synthetic_tasks(seed=1, count=0)
    with pytest.raises(ValueError, match="count exceeds"):
        generate_synthetic_tasks(seed=1, count=7, category="light")


def test_cli_can_preview_all_24_templates(capsys):
    assert main(["--seed", "3", "--count", "24"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result) == 24
    assert all(item["status"] == "preview_only_not_submitted" for item in result)


def test_cli_lists_all_24_templates_without_submitting(capsys):
    assert main(["--list"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result) == 24
    assert all("template_id" in entry for entry in result)
