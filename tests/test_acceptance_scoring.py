import copy

import pytest

from ai.execution.contract import contract_hash, make_contract, validate_contract
from ai.execution.scoring import (ScoringError, aggregate_judge_results, criteria_hash,
                                  score_acceptance, validate_criteria)


def rubric(*items):
    return [
        {"id": criterion_id, "description": criterion_id, "weight": weight, "hard_gate": hard_gate}
        for criterion_id, weight, hard_gate in items
    ]


def outcomes(criteria, passed_ids):
    return {
        item["id"]: {
            "passed": item["id"] in passed_ids,
            "evidence": f"Evidence for {item['id']}",
        }
        for item in criteria
    }


@pytest.mark.parametrize(
    ("passed_weight", "expected_status", "expected_band"),
    [
        (49, "FAILED", "BELOW_50_FIXED_FAILURE"),
        (50, "FAILED", "BASE_REWARD"),
        (74, "FAILED", "BASE_REWARD"),
        (75, "PASSED", "BASE_REWARD"),
        (76, "PASSED", "BONUS_1_50"),
        (79, "PASSED", "BONUS_1_50"),
        (80, "PASSED", "BONUS_1_75"),
        (89, "PASSED", "BONUS_1_75"),
        (90, "PASSED", "BONUS_2_00"),
        (100, "PASSED", "BONUS_2_00"),
    ],
)
def test_score_thresholds_and_reward_bands(passed_weight, expected_status, expected_band):
    criteria = rubric(("passed", passed_weight, False))
    if passed_weight < 100:
        criteria.append({"id": "failed", "description": "failed", "weight": 100 - passed_weight,
                         "hard_gate": False})
    result = score_acceptance(criteria, outcomes(criteria, {"passed"}))

    assert result["status"] == expected_status
    assert result["criteria_score_percent"] == passed_weight
    assert result["reward_band"] == expected_band


def test_hard_gate_failure_overrides_high_weighted_score_and_is_reported():
    criteria = rubric(("core", 80, False), ("required", 20, True))
    result = score_acceptance(criteria, outcomes(criteria, {"core"}))

    assert result["criteria_score_percent"] == 80
    assert result["status"] == "FAILED"
    assert result["hard_gate_passed"] is False
    assert [item["id"] for item in result["hard_gate_failures"]] == ["required"]
    assert result["failed_criteria"][0]["evidence"] == "Evidence for required"
    assert "payout treatment" in result["settlement_note"]


def test_non_hard_gate_failure_reduces_score_and_is_exposed_to_client():
    criteria = rubric(("core", 80, False), ("optional", 20, False))
    result = score_acceptance(criteria, outcomes(criteria, {"core"}))

    assert result["status"] == "PASSED"
    assert result["criteria_score_percent"] == 80
    assert [item["id"] for item in result["failed_criteria"]] == ["optional"]
    assert "Remaining failures and risks" in result["client_report_markdown"]
    assert "Evidence for optional" in result["client_report_markdown"]
    assert "not a calibrated probability" in result["client_report_markdown"]


def test_missing_or_unexpected_results_are_rejected():
    criteria = rubric(("first", 60, False), ("second", 40, False))
    with pytest.raises(ScoringError, match="missing="):
        score_acceptance(criteria, {"first": {"passed": True, "evidence": "ok"}})
    with pytest.raises(ScoringError, match="unknown="):
        score_acceptance(criteria, {**outcomes(criteria, {"first"}), "forged": {"passed": True, "evidence": "x"}})


@pytest.mark.parametrize(
    "invalid",
    [
        [],
        [{"id": "same", "description": "A", "weight": 1, "hard_gate": False},
         {"id": "same", "description": "B", "weight": 2, "hard_gate": False}],
        [{"id": "UPPER", "description": "bad id", "weight": 1, "hard_gate": False}],
        [{"id": "a", "description": "bad weight", "weight": True, "hard_gate": False}],
        [{"id": "a", "description": "bad gate", "weight": 1, "hard_gate": 1}],
    ],
)
def test_invalid_rubrics_are_rejected(invalid):
    with pytest.raises(ScoringError):
        validate_criteria(invalid)


def test_rubric_is_validated_and_committed_by_acceptance_hash():
    contract = make_contract("build a tool")
    contract["criteria"] = rubric(("works", 75, True), ("docs", 25, False))
    for criterion in contract["criteria"]:
        criterion["check"] = {"type": "application_runs"}
    normalized = validate_contract(contract)
    original_hash = contract_hash(normalized)

    changed = copy.deepcopy(normalized)
    changed["criteria"][1]["weight"] = 30
    assert criteria_hash(normalized["criteria"]) == criteria_hash(contract["criteria"])
    assert contract_hash(changed) != original_hash

    changed["criteria"][1]["weight"] = 0
    with pytest.raises(ScoringError, match="integer from 1"):
        validate_contract(changed)


def test_three_judges_use_majority_per_criterion_before_scoring():
    criteria = rubric(("core", 40, False), ("secondary", 30, False), ("launches", 30, True))
    reports = {
        "judge-a": outcomes(criteria, {"core", "secondary", "launches"}),
        "judge-b": outcomes(criteria, {"core", "launches"}),
        "judge-c": outcomes(criteria, {"launches"}),
    }

    result = aggregate_judge_results(criteria, reports)

    assert result["status"] == "FAILED"
    assert result["criteria_score_percent"] == 70
    assert result["reward_band"] == "BASE_REWARD"
    assert result["judge_agreement"] == {
        "core": {"passed": 2, "failed": 1},
        "secondary": {"passed": 1, "failed": 2},
        "launches": {"passed": 3, "failed": 0},
    }


def test_two_judge_disagreement_waits_for_third_then_resolves():
    criteria = rubric(("critical", 100, True))
    reports = {
        "judge-a": outcomes(criteria, {"critical"}),
        "judge-b": outcomes(criteria, set()),
    }

    pending = aggregate_judge_results(criteria, reports)
    assert pending["status"] == "PENDING"
    assert pending["unresolved_criteria"] == ["critical"]

    reports["judge-c"] = outcomes(criteria, set())
    resolved = aggregate_judge_results(criteria, reports)
    assert resolved["status"] == "FAILED"
    assert resolved["criteria_score_percent"] == 0
    assert resolved["hard_gate_passed"] is False


def test_two_matching_judges_form_per_criterion_majority():
    criteria = rubric(("first", 60, False), ("second", 40, False))
    reports = {
        "judge-a": outcomes(criteria, {"first"}),
        "judge-b": outcomes(criteria, {"first"}),
    }
    result = aggregate_judge_results(criteria, reports)
    assert result["status"] == "FAILED"
    assert result["criteria_score_percent"] == 60
    assert result["judge_count"] == 2


def test_judge_aggregation_rejects_more_reports_than_committee_size():
    criteria = rubric(("first", 100, False))
    reports = {f"judge-{index}": outcomes(criteria, {"first"}) for index in range(4)}
    with pytest.raises(ScoringError, match="exceeds committee_size"):
        aggregate_judge_results(criteria, reports)
