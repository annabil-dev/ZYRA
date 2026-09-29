import hashlib
import json

import ecdsa

from ai.blockchain.wallet import ZyraWallet
from p2p.votes import judge_address, sign_vote, verify_vote
from zyra_cmd.zyra_cli import get_pending_miner_task


def test_legacy_simulated_wallet_gets_signing_key_without_changing_legacy_address(tmp_path):
    wallet_dir = tmp_path / "legacy-wallet"
    wallet_dir.mkdir()
    private_key = hashlib.sha256(b"old simulated private key").hexdigest()
    public_key = hashlib.sha256(private_key.encode()).hexdigest()
    legacy_address = "Z" + hashlib.new("ripemd160", public_key.encode()).hexdigest()
    wallet_file = wallet_dir / "wallet.json"
    wallet_file.write_text(json.dumps({
        "private_key": private_key,
        "public_key": public_key,
        "address": legacy_address,
        "metamask_address": "0x" + "12" * 20,
    }))

    wallet = ZyraWallet(str(wallet_dir))
    assert wallet.address == legacy_address
    assert wallet.metamask_address == "0x" + "12" * 20
    assert judge_address(wallet.signing_public_key) == wallet.signing_address
    assert wallet.signing_address != legacy_address
    stored = json.loads(wallet_file.read_text())
    assert stored["address"] == legacy_address
    assert stored["signing_address"] == wallet.signing_address
    assert ecdsa.SigningKey.from_string(bytes.fromhex(stored["signing_private_key"]),
                                        curve=ecdsa.SECP256k1)

    miner = ZyraWallet(str(tmp_path / "miner-wallet"))
    trajectory = {"task_id": "old-task", "trajectory_hash": "trajectory",
                  "trajectory_log": "sha256:" + "a" * 64, "acceptance_hash": "contract",
                  "miner_identity": miner.signing_address, "miner_public_key": miner.signing_public_key}
    task = {"task_id": "old-task", "acceptance_hash": "contract"}
    vote = sign_vote(wallet, trajectory, "PASS")
    assert verify_vote(vote, trajectory, task)


def test_miner_task_picker_handles_empty_queue_and_feedback_priority():
    assert get_pending_miner_task({}) is None
    tasks = {
        "other": {"task_id": "other", "status": "pending"},
        "retry": {"task_id": "retry", "status": "pending", "feedback": ["fix error"]},
    }
    assert get_pending_miner_task(tasks) == ("other", tasks["other"])
    assert get_pending_miner_task(tasks, "retry") == ("retry", tasks["retry"])
    tasks["retry"]["status"] = "mining"
    assert get_pending_miner_task(tasks, "retry") == ("other", tasks["other"])


def test_miner_task_picker_respects_live_lease_and_recovers_expired_lease(tmp_path):
    import time
    from p2p.leases import create_lease, LEASE_SECONDS

    owner = ZyraWallet(str(tmp_path / "lease-owner"))
    other = ZyraWallet(str(tmp_path / "lease-other"))
    task = {"task_id": "lease-task", "status": "pending", "acceptance_hash": "contract"}
    lease = create_lease(owner, task)
    task.update(status="mining", lease=lease, attempt_id=lease["lease_id"])
    tasks = {"lease-task": task}

    assert get_pending_miner_task(tasks, miner_identity=owner.signing_address) == ("lease-task", task)
    assert get_pending_miner_task(tasks, miner_identity=other.signing_address) is None
    expired_at = lease["expires_at"] + 1
    assert get_pending_miner_task(tasks, miner_identity=other.signing_address, now=expired_at) == ("lease-task", task)
    assert time.time() < expired_at


def test_chain_mode_does_not_let_advisory_p2p_lease_hide_task():
    task = {"task_id": "chain-task", "status": "mining", "lease_mode": "mythchain",
            "lease": {"miner_identity": "another-p2p-miner"}, "attempt_id": "p2p-attempt"}
    tasks = {"chain-task": task}
    assert get_pending_miner_task(tasks, miner_identity="this-miner", canonical_mode=True) == ("chain-task", task)


def test_required_chain_mode_discovers_candidates_and_skips_claim_failures():
    advisory = {"task_id": "old-task", "status": "pending", "lease_mode": "p2p-advisory"}
    canonical = {"task_id": "chain-task", "status": "pending", "acceptance_hash": "hash"}
    tasks = {"old-task": advisory, "chain-task": canonical}

    # The mode field can be missing from a relay payload; chain claim is the authority.
    assert get_pending_miner_task(tasks, canonical_mode=True) == ("old-task", advisory)
    assert get_pending_miner_task(tasks, excluded_task_ids={"old-task"},
                                  canonical_mode=True) == ("chain-task", canonical)
    assert get_pending_miner_task(tasks, canonical_mode=True,
                                  excluded_task_ids={"old-task", "chain-task"}) is None
