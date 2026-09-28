import asyncio
import time

from ai.blockchain.wallet import ZyraWallet
from p2p.leases import LEASE_SECONDS, create_lease, verify_lease
from p2p.network import P2PNode
from p2p.protocol import MessageType, create_message, parse_message
from p2p.votes import sign_vote


def task_template():
    return {"task_id": "coding-task", "status": "pending", "acceptance_hash": "acceptance-v1",
            "prompt": "Build the requested app"}


def test_signed_claims_converge_to_same_winner_when_nodes_see_same_set(tmp_path):
    first_wallet = ZyraWallet(str(tmp_path / "miner-first"))
    second_wallet = ZyraWallet(str(tmp_path / "miner-second"))
    first_claim = create_lease(first_wallet, task_template())
    second_claim = create_lease(second_wallet, task_template())
    assert verify_lease(first_claim, task_template())
    assert verify_lease(second_claim, task_template())

    first_node, second_node = P2PNode(), P2PNode()
    first_node.tasks["coding-task"] = task_template()
    second_node.tasks["coding-task"] = task_template()
    for claim in (first_claim, second_claim):
        assert first_node.accept_task_claim(claim)
    for claim in (second_claim, first_claim):
        assert second_node.accept_task_claim(claim)

    assert first_node.tasks["coding-task"]["attempt_id"] == second_node.tasks["coding-task"]["attempt_id"]
    assert first_node.tasks["coding-task"]["lease"]["lease_id"] == min(
        first_claim["lease_id"], second_claim["lease_id"])


def test_claim_signature_tamper_and_wrong_task_are_rejected(tmp_path):
    wallet = ZyraWallet(str(tmp_path / "miner"))
    task = task_template()
    claim = create_lease(wallet, task)
    node = P2PNode()
    node.tasks[task["task_id"]] = task

    assert not node.accept_task_claim({**claim, "acceptance_hash": "forged"})
    assert not node.accept_task_claim({**claim, "miner_identity": "Zfake"})
    assert not node.accept_task_claim({**claim, "signature": "00"})
    assert node.tasks[task["task_id"]].get("lease") is None


def test_expired_lease_returns_task_to_pending_and_stale_vote_is_rejected(tmp_path):
    owner = ZyraWallet(str(tmp_path / "owner"))
    next_miner = ZyraWallet(str(tmp_path / "next"))
    judge_a = ZyraWallet(str(tmp_path / "judge-a"))
    judge_b = ZyraWallet(str(tmp_path / "judge-b"))
    task = task_template()
    node = P2PNode()
    node.tasks[task["task_id"]] = task
    old_lease = create_lease(owner, task)
    assert node.accept_task_claim(old_lease)
    old_attempt = old_lease["lease_id"]
    trajectory = {"task_id": task["task_id"], "trajectory_hash": "old-trajectory",
                  "trajectory_log": "sha256:" + "a" * 64, "acceptance_hash": task["acceptance_hash"],
                  "attempt_id": old_attempt, "miner_identity": owner.signing_address,
                  "miner_public_key": owner.signing_public_key}
    node.trajectories[trajectory["trajectory_hash"]] = trajectory

    node.expire_task_leases(now=old_lease["expires_at"] + 1)
    assert node.tasks[task["task_id"]]["status"] == "pending"
    assert node.tasks[task["task_id"]].get("lease") is None
    new_lease = create_lease(next_miner, node.tasks[task["task_id"]])
    assert node.accept_task_claim(new_lease)
    assert node.tasks[task["task_id"]]["attempt_id"] == new_lease["lease_id"]

    assert not node.accept_vote(sign_vote(judge_a, trajectory, "PASS"))
    assert not node.accept_vote(sign_vote(judge_b, trajectory, "PASS"))
    assert node.tasks[task["task_id"]]["status"] == "mining"


def test_lease_ttl_is_bounded(tmp_path):
    wallet = ZyraWallet(str(tmp_path / "wallet"))
    task = task_template()
    claim = create_lease(wallet, task)
    claim["expires_at"] = claim["issued_at"] + LEASE_SECONDS * 100
    assert not verify_lease(claim, task)


def test_claim_gossip_and_mempool_sync_restore_the_verified_lease(tmp_path):
    async def scenario():
        miner = ZyraWallet(str(tmp_path / "miner"))
        source = P2PNode()
        task = task_template()
        source.tasks[task["task_id"]] = task
        claim = create_lease(miner, task)
        raw_claim = create_message(MessageType.TASK_CLAIM, claim)
        await source.handle_message(parse_message(raw_claim), None, raw_claim)
        assert source.tasks[task["task_id"]]["lease"]["lease_id"] == claim["lease_id"]

        target = P2PNode()
        target.tasks[task["task_id"]] = task_template()
        sync = create_message(MessageType.MEMPOOL_DATA, {
            "tasks": source.tasks,
            "trajectories": {},
            "signatures": {},
            "task_claims": source.task_claims,
        })
        await target.handle_message(parse_message(sync), None, sync)
        restored = target.tasks[task["task_id"]]
        assert restored["lease"]["lease_id"] == claim["lease_id"]
        assert restored["attempt_id"] == claim["lease_id"]
        assert restored["status"] == "mining"
    asyncio.run(scenario())
