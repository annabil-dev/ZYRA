"""Signed PoUW votes. Quorum is a prototype, not Sybil-resistant consensus."""

import hashlib
import json

import ecdsa

QUORUM = 2
DOMAIN = "ZYRA-POUW-VOTE-v1"


def judge_address(public_key):
    if not isinstance(public_key, str) or len(public_key) != 128:
        raise ValueError("Invalid judge public key")
    bytes.fromhex(public_key)
    return "Z" + hashlib.sha256(public_key.encode()).hexdigest()[:40]


def vote_bytes(vote):
    fields = ("task_id", "trajectory_hash", "trajectory_log", "acceptance_hash", "verdict", "reason")
    if not isinstance(vote, dict) or any(not isinstance(vote.get(field), str) or not vote[field] for field in fields[:5]):
        raise ValueError("Incomplete vote")
    if vote["verdict"] not in ("PASS", "FAIL") or not isinstance(vote["reason"], str) or len(vote["reason"]) > 2000:
        raise ValueError("Invalid verdict or reason")
    return json.dumps({"domain": DOMAIN, **{field: vote[field] for field in fields}},
                      sort_keys=True, separators=(",", ":")).encode()


def sign_vote(wallet, trajectory, verdict, reason=""):
    vote = {field: trajectory[field] for field in ("task_id", "trajectory_hash", "trajectory_log", "acceptance_hash")}
    vote.update(verdict=verdict, reason=str(reason)[:2000], public_key=wallet.public_key)
    vote["judge_wallet"] = judge_address(wallet.public_key)
    key = ecdsa.SigningKey.from_string(bytes.fromhex(wallet.private_key), curve=ecdsa.SECP256k1)
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
        if any(vote.get(field) != trajectory.get(field) for field in
               ("task_id", "trajectory_hash", "trajectory_log", "acceptance_hash")):
            return False
        if vote.get("judge_wallet") != judge_address(vote.get("public_key")):
            return False
        if vote["judge_wallet"] in (trajectory.get("miner_identity"), trajectory.get("wallet")):
            return False
        if vote.get("public_key") == trajectory.get("miner_public_key"):
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
