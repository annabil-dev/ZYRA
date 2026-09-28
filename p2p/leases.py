"""Best-effort, signed P2P work leases. Chain consensus is still required for finality."""

import hashlib
import json
import time
import uuid

import ecdsa

from p2p.votes import judge_address

LEASE_SECONDS = 30 * 60
MAX_LEASE_SECONDS = 60 * 60
CLAIM_SETTLE_SECONDS = 3
DOMAIN = "ZYRA-TASK-LEASE-v1"


def lease_bytes(lease):
    fields = ("task_id", "acceptance_hash", "lease_id", "miner_identity", "public_key", "issued_at", "expires_at")
    return json.dumps({"domain": DOMAIN, **{key: lease[key] for key in fields}},
                      sort_keys=True, separators=(",", ":")).encode()


def create_lease(wallet, task, now=None):
    public_key = getattr(wallet, "signing_public_key", None) or wallet.public_key
    private_key = getattr(wallet, "signing_private_key", None) or wallet.private_key
    issued_at = float(time.time() if now is None else now)
    lease = {
        "task_id": task["task_id"],
        "acceptance_hash": task["acceptance_hash"],
        "lease_id": uuid.uuid4().hex,
        "miner_identity": judge_address(public_key),
        "public_key": public_key,
        "issued_at": issued_at,
        "expires_at": issued_at + LEASE_SECONDS,
    }
    key = ecdsa.SigningKey.from_string(bytes.fromhex(private_key), curve=ecdsa.SECP256k1)
    lease["signature"] = key.sign_deterministic(lease_bytes(lease), hashfunc=hashlib.sha256).hex()
    return lease


def verify_lease(lease, task, now=None):
    try:
        if not isinstance(lease, dict) or not isinstance(task, dict):
            return False
        if lease.get("task_id") != task.get("task_id") or lease.get("acceptance_hash") != task.get("acceptance_hash"):
            return False
        if lease.get("miner_identity") != judge_address(lease.get("public_key")):
            return False
        issued, expiry = float(lease["issued_at"]), float(lease["expires_at"])
        current = float(time.time() if now is None else now)
        if expiry <= current or expiry <= issued or expiry - issued > MAX_LEASE_SECONDS:
            return False
        if issued > current + 60:
            return False
        key = ecdsa.VerifyingKey.from_string(bytes.fromhex(lease["public_key"]), curve=ecdsa.SECP256k1)
        return key.verify(bytes.fromhex(lease["signature"]), lease_bytes(lease), hashfunc=hashlib.sha256)
    except (ValueError, KeyError, TypeError, ecdsa.BadSignatureError, ecdsa.MalformedPointError):
        return False


def lease_order(lease):
    """A total deterministic preference among concurrent signed claims."""
    return lease["lease_id"]
