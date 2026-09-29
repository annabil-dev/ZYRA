"""Deterministic weighted acceptance scoring and client-facing failure reports."""

import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction


class ScoringError(ValueError):
    """Invalid rubric or incomplete/unverifiable criterion results."""


_CRITERION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_CRITERION_FIELDS = {"id", "description", "weight", "hard_gate", "check"}
_REQUIRED_CRITERION_FIELDS = {"id", "description", "weight", "hard_gate"}
MAX_CRITERIA = 100
MAX_CRITERION_WEIGHT = 1_000_000
MAX_TOTAL_CRITERION_WEIGHT = 1_000_000
MAX_CRITERION_EVIDENCE_LENGTH = 1000


def validate_criteria(criteria):
    """Validate an immutable task rubric with positive integer weights."""
    if not isinstance(criteria, list) or not criteria:
        raise ScoringError("criteria must be a non-empty list")
    if len(criteria) > MAX_CRITERIA:
        raise ScoringError(f"criteria cannot contain more than {MAX_CRITERIA} entries")

    normalized = []
    seen = set()
    total_weight = 0
    for index, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            raise ScoringError(f"criteria[{index}] must be an object")
        unknown = set(criterion) - _CRITERION_FIELDS
        missing = _REQUIRED_CRITERION_FIELDS - set(criterion)
        if unknown or missing:
            raise ScoringError(
                f"criteria[{index}] fields invalid; missing={sorted(missing)}, unknown={sorted(unknown)}"
            )

        criterion_id = criterion["id"]
        description = criterion["description"]
        weight = criterion["weight"]
        hard_gate = criterion["hard_gate"]
        if not isinstance(criterion_id, str) or not _CRITERION_ID.fullmatch(criterion_id):
            raise ScoringError(f"criteria[{index}].id must be a stable lowercase identifier")
        if criterion_id in seen:
            raise ScoringError(f"Duplicate criterion id: {criterion_id}")
        if not isinstance(description, str) or not description.strip():
            raise ScoringError(f"criteria[{index}].description must not be empty")
        if len(description.encode("utf-8")) > 500:
            raise ScoringError(f"criteria[{index}].description is too long")
        if isinstance(weight, bool) or not isinstance(weight, int) or not 1 <= weight <= MAX_CRITERION_WEIGHT:
            raise ScoringError(f"criteria[{index}].weight must be an integer from 1 to {MAX_CRITERION_WEIGHT}")
        if not isinstance(hard_gate, bool):
            raise ScoringError(f"criteria[{index}].hard_gate must be a boolean")

        seen.add(criterion_id)
        total_weight += weight
        if total_weight > MAX_TOTAL_CRITERION_WEIGHT:
            raise ScoringError(f"total criterion weight cannot exceed {MAX_TOTAL_CRITERION_WEIGHT}")
        normalized.append({
            "id": criterion_id,
            "description": description.strip(),
            "weight": weight,
            "hard_gate": hard_gate,
            **({"check": criterion["check"]} if "check" in criterion else {}),
        })
    return normalized


def criteria_hash(criteria):
    """Return a stable SHA-256 commitment to the rubric."""
    normalized = validate_criteria(criteria)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _score_band(score):
    """Classify exact rational scores without float-boundary ambiguity."""
    if score < 50:
        return "BELOW_50_FIXED_FAILURE"
    if score <= 75:
        return "BASE_REWARD"
    if score < 80:
        return "BONUS_1_50"
    if score < 90:
        return "BONUS_1_75"
    return "BONUS_2_00"


def format_client_report(result):
    """Render a transparent Markdown report from a score result."""
    def cell(value):
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")

    lines = [
        "## Acceptance review",
        "",
        f"- **Result:** {result['status']}",
        f"- **Weighted criteria score:** {result['criteria_score_percent']:.2f}%",
        f"- **Hard gates:** {'PASS' if result['hard_gate_passed'] else 'FAIL'}",
        f"- **Reward band:** {result['reward_band']} (classification only; no token settlement performed)",
        "",
        "| Criterion | Weight | Hard gate | Result | Evidence |",
        "|---|---:|:---:|:---:|---|",
    ]
    for criterion in result["criteria"]:
        lines.append(
            f"| {cell(criterion['description'])} ({cell(criterion['id'])}) "
            f"| {criterion['weight']} | {'Yes' if criterion['hard_gate'] else 'No'} "
            f"| {'PASS' if criterion['passed'] else 'FAIL'} | {cell(criterion['evidence'])} |"
        )

    failures = result["failed_criteria"]
    if failures:
        lines.extend(("", "### Remaining failures and risks", ""))
        for criterion in failures:
            gate = "Hard gate" if criterion["hard_gate"] else "Weighted criterion"
            lines.append(
                f"- **{cell(criterion['description'])}** ({gate}, weight {criterion['weight']}): "
                f"{cell(criterion['evidence'])}"
            )
    else:
        lines.extend(("", "All declared acceptance criteria passed.",))

    if result.get("settlement_note"):
        lines.extend(("", f"> {cell(result['settlement_note'])}"))
    lines.extend(("", "This score measures weighted acceptance criteria; it is not a calibrated probability of success."))
    return "\n".join(lines)


def score_acceptance(criteria, results):
    """Score criterion outcomes and return transparent per-criterion evidence.

    ``results`` maps each criterion id to ``{"passed": bool, "evidence": str}``.
    Missing results are rejected rather than silently treated as passes or failures.
    This function calculates a criteria score; it does not transfer or settle tokens.
    """
    rubric = validate_criteria(criteria)
    if not isinstance(results, dict):
        raise ScoringError("results must be an object keyed by criterion id")

    expected_ids = {criterion["id"] for criterion in rubric}
    result_ids = set(results)
    if result_ids != expected_ids:
        missing = sorted(expected_ids - result_ids)
        unknown = sorted(result_ids - expected_ids)
        raise ScoringError(f"Criterion results mismatch; missing={missing}, unknown={unknown}")

    total_weight = sum(criterion["weight"] for criterion in rubric)
    passed_weight = 0
    failed_criteria = []
    hard_gate_failures = []
    criterion_reports = []

    for criterion in rubric:
        outcome = results[criterion["id"]]
        if not isinstance(outcome, dict) or set(outcome) - {"passed", "evidence"}:
            raise ScoringError(f"Result for {criterion['id']} must contain passed and evidence only")
        if "passed" not in outcome or not isinstance(outcome["passed"], bool):
            raise ScoringError(f"Result for {criterion['id']} needs a boolean passed value")
        evidence = outcome.get("evidence")
        if (not isinstance(evidence, str) or not evidence.strip()
                or len(evidence.strip().encode("utf-8")) > MAX_CRITERION_EVIDENCE_LENGTH):
            raise ScoringError(
                f"Result for {criterion['id']} needs evidence between 1 and {MAX_CRITERION_EVIDENCE_LENGTH} characters"
            )

        report = {
            **criterion,
            "passed": outcome["passed"],
            "evidence": evidence.strip(),
        }
        criterion_reports.append(report)
        if outcome["passed"]:
            passed_weight += criterion["weight"]
        else:
            failed_criteria.append(report)
            if criterion["hard_gate"]:
                hard_gate_failures.append(report)

    score = Fraction(passed_weight * 100, total_weight)
    score_display = (Decimal(passed_weight * 100) / Decimal(total_weight)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    task_passed = score >= 75 and not hard_gate_failures

    score_result = {
        "status": "PASSED" if task_passed else "FAILED",
        "criteria_score_percent": float(score_display),
        "score_numerator": passed_weight,
        "score_denominator": total_weight,
        "minimum_passing_percent": 75,
        "hard_gate_passed": not hard_gate_failures,
        "hard_gate_failures": hard_gate_failures,
        "reward_band": _score_band(score),
        "settlement_note": (
            "Hard-gate failure overrides the score for task pass status; payout treatment for this case is not encoded."
            if hard_gate_failures else None
        ),
        "criteria": criterion_reports,
        "failed_criteria": failed_criteria,
    }
    score_result["client_report_markdown"] = format_client_report(score_result)
    return score_result


def aggregate_judge_results(criteria, judge_results, *, committee_size=3, majority=2):
    """Resolve per-criterion outcomes by judge majority, then score the result.

    A 1-1 criterion split remains pending when only two judges have reported.
    The third judge can resolve it by creating a 2-1 majority. Two matching
    reports are sufficient for a criterion-level majority. This helper does not
    authenticate judges or perform chain settlement; callers must verify votes.
    """
    rubric = validate_criteria(criteria)
    if not isinstance(judge_results, dict):
        raise ScoringError("judge_results must map unique judge IDs to criterion results")
    if isinstance(committee_size, bool) or not isinstance(committee_size, int) or committee_size < 2:
        raise ScoringError("committee_size must be an integer of at least 2")
    if isinstance(majority, bool) or not isinstance(majority, int) or not 1 < majority <= committee_size:
        raise ScoringError("majority must be greater than 1 and no larger than committee_size")
    if len(judge_results) > committee_size:
        raise ScoringError("judge_results exceeds committee_size")
    if not all(isinstance(judge_id, str) and judge_id.strip() for judge_id in judge_results):
        raise ScoringError("judge IDs must be non-empty strings")

    for outcomes in judge_results.values():
        # Validate completeness, evidence, and types before counting a judge's vote.
        score_acceptance(rubric, outcomes)

    if len(judge_results) < majority:
        return {
            "status": "PENDING",
            "judge_count": len(judge_results),
            "required_majority": majority,
            "unresolved_criteria": [criterion["id"] for criterion in rubric],
            "reason": "Waiting for enough independent judge reports.",
        }

    canonical_results = {}
    unresolved = []
    agreement = {}
    for criterion in rubric:
        criterion_id = criterion["id"]
        pass_judges = [judge_id for judge_id, results in judge_results.items()
                       if results[criterion_id]["passed"]]
        fail_judges = [judge_id for judge_id, results in judge_results.items()
                       if not results[criterion_id]["passed"]]
        agreement[criterion_id] = {"passed": len(pass_judges), "failed": len(fail_judges)}

        if len(pass_judges) >= majority:
            selected = True
            agreeing_judges = pass_judges
        elif len(fail_judges) >= majority:
            selected = False
            agreeing_judges = fail_judges
        else:
            unresolved.append(criterion_id)
            continue

        evidence = " | ".join(
            f"{judge_id}: {judge_results[judge_id][criterion_id]['evidence']}"
            for judge_id in agreeing_judges
        )
        canonical_results[criterion_id] = {"passed": selected, "evidence": evidence}

    if unresolved:
        return {
            "status": "PENDING",
            "judge_count": len(judge_results),
            "required_majority": majority,
            "unresolved_criteria": unresolved,
            "agreement": agreement,
            "reason": "Waiting for another judge to resolve per-criterion disagreement.",
        }

    result = score_acceptance(rubric, canonical_results)
    result["judge_count"] = len(judge_results)
    result["required_majority"] = majority
    result["judge_agreement"] = agreement
    result["canonical_results"] = canonical_results
    result["client_report_markdown"] = format_client_report(result)
    return result
