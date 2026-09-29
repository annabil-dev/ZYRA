"""Signed PoUW votes. Quorum is a prototype, not Sybil-resistant consensus."""

import hashlib
import json

import ecdsa

from ai.execution.scoring import ScoringError, aggregate_judge_results, score_acceptance

QUORUM = 2
JUDGE_COMMITTEE_SIZE = 3
CRITERIA_MAJORITY = 2
DOMAIN = "ZYRA-POUW-VOTE-v1"


def judge_address(public_key):
    if not isinstance(public_key, str) or len(public_key) != 128:
        raise ValueError("Invalid judge public key")
    bytes.fromhex(public_key)
    return "Z" + hashlib.sha256(public_key.encode()).hexdigest()[:40]


def vote_bytes(vote):
    fields = ("task_id", "trajectory_hash", "trajectory_log", "acceptance_hash", "attempt_id", "verdict", "reason")
    if not isinstance(vote, dict) or any(not isinstance(vote.get(field), str) or not vote[field] for field in fields[:4]):
        raise ValueError("Incomplete vote")
    if not isinstance(vote.get("attempt_id", ""), str):
        raise ValueError("Invalid attempt ID")
    if vote["verdict"] not in ("PASS", "FAIL") or not isinstance(vote["reason"], str) or len(vote["reason"]) > 2000:
        raise ValueError("Invalid verdict or reason")
    payload = {"domain": DOMAIN, **{field: vote[field] for field in fields}}
    if "criteria_results" in vote:
        payload["criteria_results"] = vote["criteria_results"]
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign_vote(wallet, trajectory, verdict, reason="", criteria_results=None):
    vote = {field: trajectory[field] for field in ("task_id", "trajectory_hash", "trajectory_log", "acceptance_hash")}
    vote["attempt_id"] = trajectory.get("attempt_id", "")
    public_key = getattr(wallet, "signing_public_key", None) or wallet.public_key
    private_key = getattr(wallet, "signing_private_key", None) or wallet.private_key
    vote.update(verdict=verdict, reason=str(reason)[:2000], public_key=public_key)
    if criteria_results is not None:
        vote["criteria_results"] = criteria_results
    vote["judge_wallet"] = judge_address(public_key)
    key = ecdsa.SigningKey.from_string(bytes.fromhex(private_key), curve=ecdsa.SECP256k1)
    vote["signature"] = key.sign_deterministic(vote_bytes(vote), hashfunc=hashlib.sha256).hex()
    return vote


def verify_vote(vote, trajectory, task):
    try:
        if not isinstance(vote, dict) or not isinstance(trajectory, dict) or not isinstance(task, dict):
            return False
        if task.get("task_id") != trajectory.get("task_id") or task.get("acceptance_hash") != trajectory.get("acceptance_hash"):
            return False
        if task.get("trajectory_hash") and task["trajectory_hash"] != trajectory.get("trajectory_hash"):
            return False
        if task.get("attempt_id") and task["attempt_id"] != trajectory.get("attempt_id"):
            return False
        if trajectory.get("attempt_id") and (
                not task.get("lease") or task["lease"].get("lease_id") != trajectory["attempt_id"]):
            return False
        if any(vote.get(field) != trajectory.get(field) for field in
               ("task_id", "trajectory_hash", "trajectory_log", "acceptance_hash")):
            return False
        if vote.get("attempt_id", "") != trajectory.get("attempt_id", ""):
            return False
        if vote.get("judge_wallet") != judge_address(vote.get("public_key")):
            return False
        if vote["judge_wallet"] in (trajectory.get("miner_identity"), trajectory.get("wallet")):
            return False
        if vote.get("public_key") == trajectory.get("miner_public_key"):
            return False
        acceptance = task.get("acceptance") or {}
        criteria = acceptance.get("criteria") if isinstance(acceptance, dict) else None
        if criteria:
            if "criteria_results" not in vote:
                return False
            from ai.execution.contract import contract_hash
            if contract_hash(acceptance) != trajectory.get("acceptance_hash"):
                return False
            score = score_acceptance(criteria, vote["criteria_results"])
            expected_verdict = "PASS" if score["status"] == "PASSED" else "FAIL"
            if vote.get("verdict") != expected_verdict:
                return False
        elif "criteria_results" in vote:
            return False
        vk = ecdsa.VerifyingKey.from_string(bytes.fromhex(vote["public_key"]), curve=ecdsa.SECP256k1)
        return vk.verify(bytes.fromhex(vote["signature"]), vote_bytes(vote), hashfunc=hashlib.sha256)
    except (ValueError, KeyError, TypeError, ecdsa.BadSignatureError, ecdsa.MalformedPointError):
        return False


def tally(votes):
    """Equivocating judge IDs never count towards either verdict."""
    passed = sum(v["verdict"] == "PASS" for v in votes.values())
    failed = sum(v["verdict"] == "FAIL" for v in votes.values())
    if passed >= QUORUM:
        return "PASS"
    if failed >= QUORUM:
        return "FAIL"
    return None


def tally_criteria_votes(votes, criteria):
    """Return pending or a weighted result from per-criterion judge majorities."""
    if not isinstance(votes, dict) or len(votes) > JUDGE_COMMITTEE_SIZE:
        raise ValueError("Criteria votes must contain at most three distinct judges")
    try:
        return aggregate_judge_results(
            criteria,
            {judge: vote["criteria_results"] for judge, vote in votes.items()},
            committee_size=JUDGE_COMMITTEE_SIZE,
            majority=CRITERIA_MAJORITY,
        )
    except (KeyError, ScoringError) as exc:
        raise ValueError(f"Invalid per-criterion judge vote: {exc}") from exc
