import json

import pytest

from ai.execution.contract import contract_hash, validate_contract
from zyra_cmd.synthetic_tasks import catalog, generate_synthetic_tasks, main


def test_synthetic_preview_selection_is_reproducible():
    first = generate_synthetic_tasks(seed=2718, count=3)
    second = generate_synthetic_tasks(seed=2718, count=3)

    assert first == second
    assert len({task["preview_id"] for task in first}) == 3
    assert all(task["status"] == "preview_only_not_submitted" for task in first)
    assert all(task["reward_mode"] == "none" for task in first)
    assert all(task["origin"] == "synthetic" for task in first)


def test_synthetic_categories_have_valid_executable_acceptance_contracts():
    categories = {entry["category"] for entry in catalog()}
    assert categories == {"python-cli", "json", "text-processing", "flask-web"}

    for category in categories:
        task, = generate_synthetic_tasks(seed=17, category=category)
        acceptance = validate_contract(task["acceptance"])
        assert task["acceptance_hash"] == contract_hash(acceptance)
        assert acceptance["criteria"]
        assert all("check" in criterion for criterion in acceptance["criteria"])
        assert task["runtime_profile"] == acceptance["profile"]


def test_synthetic_generator_rejects_invalid_category_and_count():
    with pytest.raises(ValueError, match="Unknown synthetic task category"):
        generate_synthetic_tasks(seed=1, category="unknown")
    with pytest.raises(ValueError, match="count must be between"):
        generate_synthetic_tasks(seed=1, count=0)
    with pytest.raises(ValueError, match="count exceeds"):
        generate_synthetic_tasks(seed=1, count=2, category="json")


def test_cli_is_preview_only_and_prints_acceptance_hash(capsys):
    assert main(["--seed", "3", "--category", "python-cli"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert len(result) == 1
    assert result[0]["status"] == "preview_only_not_submitted"
    assert result[0]["reward_mode"] == "none"
    assert len(result[0]["acceptance_hash"]) == 64


def test_cli_can_list_templates_without_selecting_or_submitting_tasks(capsys):
    assert main(["--list"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result) == len(catalog())
    assert all("template_id" in entry for entry in result)
