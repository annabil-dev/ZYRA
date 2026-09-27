import asyncio
from ai.blockchain.ledger import ZyraLedger
from ai.blockchain.wallet import ZyraWallet
from p2p.network import P2PNode
from p2p.protocol import MessageType, create_message, parse_message
from p2p.votes import sign_vote


def setup_node(tmp_path):
    miner = ZyraWallet(str(tmp_path / "miner"))
    node = P2PNode()
    node.tasks["task"] = {"task_id": "task", "prompt": "Build an app", "status": "validating", "acceptance_hash": "acceptance"}
    node.trajectories["hash"] = {"task_id": "task", "trajectory_hash": "hash", "trajectory_log": "zip-cid",
                                 "acceptance_hash": "acceptance", "miner_identity": miner.address,
                                 "miner_public_key": miner.public_key, "status": "pending_validation"}
    return node, miner


def judge(tmp_path, name):
    return ZyraWallet(str(tmp_path / name))


def test_two_verified_votes_and_idempotent_ledger(tmp_path):
    node, miner = setup_node(tmp_path)
    ledger = ZyraLedger(str(tmp_path / "ledger"))
    one = sign_vote(judge(tmp_path, "judge-a"), node.trajectories["hash"], "PASS")
    two = sign_vote(judge(tmp_path, "judge-b"), node.trajectories["hash"], "PASS")
    assert node.add_signature(one)
    assert node.tasks["task"]["status"] == "validating"
    assert not node.add_signature(one)
    assert node.add_signature(two)
    assert node.tasks["task"]["status"] == "completed"
    assert node.tasks["task"]["result_cid"] == "zip-cid"
    assert len(node.signatures["hash"]) == 2
    first = ledger.add_pouw_reward(miner.address, 2.5, {"proof_hash": "hash"}, task_id="task")
    second = ledger.add_pouw_reward(miner.address, 2.5, {"proof_hash": "hash"}, task_id="task")
    assert first == second
    assert ZyraLedger(str(tmp_path / "ledger")).get_balance(miner.address) == 2.5


def test_forged_replay_and_self_votes_rejected(tmp_path):
    node, miner = setup_node(tmp_path)
    valid = sign_vote(judge(tmp_path, "judge-a"), node.trajectories["hash"], "PASS")
    for field, value in (("verdict", "FAIL"), ("task_id", "another"), ("trajectory_log", "different"),
                         ("acceptance_hash", "different"), ("judge_wallet", "Zfake"), ("reason", "tampered")):
        forged = {**valid, field: value}
        assert not node.add_signature(forged), field
    assert not node.add_signature({"trajectory_hash": "hash", "signature": "SIG_fake"})
    assert not node.add_signature(sign_vote(miner, node.trajectories["hash"], "PASS"))
    assert not node.signatures.get("hash")


def test_failed_quorum_returns_feedback_for_retry(tmp_path):
    node, _ = setup_node(tmp_path)
    a = sign_vote(judge(tmp_path, "a"), node.trajectories["hash"], "FAIL", "ImportError: missing dependency")
    b = sign_vote(judge(tmp_path, "b"), node.trajectories["hash"], "FAIL", "HTTP endpoint returns 500")
    assert node.add_signature(a)
    assert node.tasks["task"]["status"] == "validating"
    assert node.add_signature(b)
    task = node.tasks["task"]
    assert task["status"] == "pending"
    assert len(task["feedback"]) == 2
    assert "ImportError" in task["prompt"] and "HTTP endpoint" in task["prompt"]
    assert node.trajectories["hash"]["status"] == "rejected"


def test_unverified_update_or_snapshot_cannot_complete_task(tmp_path):
    async def scenario():
        node, _ = setup_node(tmp_path)
        altered = dict(node.tasks["task"], status="completed", result_cid="fake")
        raw = create_message(MessageType.TASK_UPDATED, altered)
        await node.handle_message(parse_message(raw), None, raw)
        assert node.tasks["task"]["status"] == "validating"
        assert node.tasks["task"].get("result_cid") != "fake"
        raw = create_message(MessageType.MEMPOOL_DATA, {"tasks": {"task": altered},
                                                       "trajectories": {}, "signatures": {"hash": ["SIG_fake"]}})
        await node.handle_message(parse_message(raw), None, raw)
        assert node.tasks["task"]["status"] == "validating"
        assert node.signatures.get("hash") is None
    asyncio.run(scenario())


def test_signed_votes_survive_mempool_sync(tmp_path):
    async def scenario():
        source, _ = setup_node(tmp_path)
        source.add_signature(sign_vote(judge(tmp_path, "a"), source.trajectories["hash"], "PASS"))
        source.add_signature(sign_vote(judge(tmp_path, "b"), source.trajectories["hash"], "PASS"))
        target = P2PNode()
        raw = create_message(MessageType.MEMPOOL_DATA, {"tasks": source.tasks, "trajectories": source.trajectories,
                                                       "signatures": source.signatures})
        await target.handle_message(parse_message(raw), None, raw)
        assert target.tasks["task"]["status"] == "completed"
        assert target.tasks["task"]["result_cid"] == "zip-cid"
    asyncio.run(scenario())


def test_votes_over_gossip_require_real_signature_and_second_judge(tmp_path):
    async def scenario():
        node, _ = setup_node(tmp_path)
        first = sign_vote(judge(tmp_path, "a"), node.trajectories["hash"], "PASS")
        forged = {**first, "verdict": "FAIL"}
        for vote in (forged, first):
            raw = create_message(MessageType.VALIDATION_SIGNATURE, vote)
            await node.handle_message(parse_message(raw), None, raw)
        assert node.tasks["task"]["status"] == "validating"
        second = sign_vote(judge(tmp_path, "b"), node.trajectories["hash"], "PASS")
        raw = create_message(MessageType.VALIDATION_SIGNATURE, second)
        await node.handle_message(parse_message(raw), None, raw)
        assert node.tasks["task"]["status"] == "completed"
    asyncio.run(scenario())
