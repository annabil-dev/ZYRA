import asyncio
import websockets
from ai.blockchain.ledger import ZyraLedger
from ai.blockchain.wallet import ZyraWallet
from p2p.network import P2PNode
from p2p.protocol import MessageType, create_message, parse_message
from p2p.votes import sign_vote
from ai.execution.contract import contract_hash, make_contract


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


def setup_weighted_node(tmp_path, criteria):
    node, miner = setup_node(tmp_path)
    acceptance = make_contract("Build a task with weighted checks")
    acceptance["criteria"] = [
        {**criterion, "check": criterion.get("check", {"type": "application_runs"})}
        for criterion in criteria
    ]
    accepted_hash = contract_hash(acceptance)
    node.tasks["task"].update(acceptance=acceptance, acceptance_hash=accepted_hash)
    node.trajectories["hash"]["acceptance_hash"] = accepted_hash
    return node, miner


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


def test_weighted_votes_use_three_judge_majority_per_criterion(tmp_path):
    criteria = [
        {"id": "core", "description": "Core feature works", "weight": 40, "hard_gate": False},
        {"id": "secondary", "description": "Secondary feature works", "weight": 30, "hard_gate": False},
        {"id": "launches", "description": "Application launches", "weight": 30, "hard_gate": True},
    ]
    node, _ = setup_weighted_node(tmp_path, criteria)

    reports = [
        ("judge-a", {"core", "secondary", "launches"}, "PASS"),
        ("judge-b", {"core", "launches"}, "FAIL"),
        ("judge-c", {"launches"}, "FAIL"),
    ]
    for name, passed, verdict in reports:
        results = {
            criterion["id"]: {"passed": criterion["id"] in passed, "evidence": f"{name} checked it"}
            for criterion in criteria
        }
        vote = sign_vote(judge(tmp_path, name), node.trajectories["hash"], verdict,
                         criteria_results=results)
        assert node.add_signature(vote)

    task = node.tasks["task"]
    assert task["status"] == "pending"
    score_report = task["acceptance_score_report"]
    assert score_report["criteria_score_percent"] == 70
    assert score_report["status"] == "FAILED"
    assert score_report["judge_agreement"]["secondary"] == {"passed": 1, "failed": 2}
    assert [item["id"] for item in score_report["failed_criteria"]] == ["secondary"]
    assert any(item.get("criterion_id") == "secondary" for item in task["feedback"])


def test_weighted_one_to_one_waits_for_third_judge(tmp_path):
    criteria = [{"id": "required", "description": "Required behavior", "weight": 100, "hard_gate": True}]
    node, _ = setup_weighted_node(tmp_path, criteria)

    first_results = {"required": {"passed": True, "evidence": "Judge A observed pass"}}
    second_results = {"required": {"passed": False, "evidence": "Judge B observed failure"}}
    first = sign_vote(judge(tmp_path, "judge-a"), node.trajectories["hash"], "PASS",
                      criteria_results=first_results)
    second = sign_vote(judge(tmp_path, "judge-b"), node.trajectories["hash"], "FAIL",
                       criteria_results=second_results)

    assert node.add_signature(first)
    assert node.add_signature(second)
    assert node.tasks["task"]["status"] == "validating"
    assert "acceptance_score_report" not in node.tasks["task"]

    third_results = {"required": {"passed": False, "evidence": "Judge C observed failure"}}
    third = sign_vote(judge(tmp_path, "judge-c"), node.trajectories["hash"], "FAIL",
                      criteria_results=third_results)
    assert node.add_signature(third)
    assert node.tasks["task"]["acceptance_score_report"]["criteria_score_percent"] == 0
    assert node.tasks["task"]["acceptance_score_report"]["hard_gate_passed"] is False


def test_weighted_votes_bind_results_verdict_and_rubric_hash(tmp_path):
    criteria = [{"id": "required", "description": "Required behavior", "weight": 100, "hard_gate": False}]
    node, _ = setup_weighted_node(tmp_path, criteria)
    results = {"required": {"passed": True, "evidence": "The check passed"}}
    wallet = judge(tmp_path, "judge-a")

    vote = sign_vote(wallet, node.trajectories["hash"], "PASS", criteria_results=results)
    forged_results = {**vote, "criteria_results": {"required": {"passed": False, "evidence": "changed"}}}
    assert not node.add_signature(forged_results)

    wrong_verdict = sign_vote(judge(tmp_path, "judge-b"), node.trajectories["hash"], "FAIL",
                              criteria_results=results)
    assert not node.add_signature(wrong_verdict)

    node.tasks["task"]["acceptance"]["criteria"][0]["weight"] = 90
    assert not node.add_signature(vote)


def test_weighted_score_report_is_rebuilt_from_signed_votes_during_sync(tmp_path):
    criteria = [{"id": "required", "description": "Required behavior", "weight": 100, "hard_gate": False}]
    source, _ = setup_weighted_node(tmp_path, criteria)
    for name in ("judge-a", "judge-b"):
        result = {"required": {"passed": True, "evidence": f"{name} passed"}}
        vote = sign_vote(judge(tmp_path, name), source.trajectories["hash"], "PASS",
                         criteria_results=result)
        assert source.add_signature(vote)

    target = P2PNode()
    payload_task = dict(source.tasks["task"])
    payload_task["acceptance_score_report"] = {"status": "FORGED"}
    payload_task["canonical_criteria_results"] = {"required": {"passed": False}}
    raw = create_message(MessageType.MEMPOOL_DATA, {
        "tasks": {"task": payload_task},
        "trajectories": source.trajectories,
        "signatures": source.signatures,
        "task_claims": {},
    })
    asyncio.run(target.handle_message(parse_message(raw), None, raw))

    assert target.tasks["task"]["status"] == "completed"
    assert target.tasks["task"]["acceptance_score_report"]["criteria_score_percent"] == 100
    assert target.tasks["task"]["acceptance_score_report"]["status"] == "PASSED"


def test_unverified_task_update_cannot_inject_weighted_score_report(tmp_path):
    async def scenario():
        criteria = [{"id": "required", "description": "Required behavior", "weight": 100, "hard_gate": False}]
        node, _ = setup_weighted_node(tmp_path, criteria)
        altered = dict(node.tasks["task"], status="completed", result_cid="fake",
                       acceptance_score_report={"status": "PASSED", "criteria_score_percent": 100},
                       canonical_criteria_results={"required": {"passed": True}})
        raw = create_message(MessageType.TASK_UPDATED, altered)
        await node.handle_message(parse_message(raw), None, raw)
        assert node.tasks["task"]["status"] == "validating"
        assert "acceptance_score_report" not in node.tasks["task"]
        assert "canonical_criteria_results" not in node.tasks["task"]

    asyncio.run(scenario())


def test_three_weighted_judges_reach_canonical_score_over_live_p2p_relay(tmp_path):
    async def scenario():
        criteria = [
            {"id": "core", "description": "Core behavior", "weight": 40, "hard_gate": False},
            {"id": "detail", "description": "Detail behavior", "weight": 30, "hard_gate": False},
            {"id": "starts", "description": "Application starts", "weight": 30, "hard_gate": True},
        ]
        relay, _ = setup_weighted_node(tmp_path, criteria)
        relay.loop = asyncio.get_running_loop()
        judges = []
        wallets = []
        for index in range(3):
            node = P2PNode()
            node.loop = asyncio.get_running_loop()
            judges.append(node)
            wallets.append(judge(tmp_path, f"live-judge-{index}"))

        async with websockets.serve(relay.handle_client, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            connections = [asyncio.create_task(node.connect_to_peer(f"ws://127.0.0.1:{port}"))
                           for node in judges]
            try:
                for _ in range(200):
                    if all("task" in node.tasks and "hash" in node.trajectories for node in judges):
                        break
                    await asyncio.sleep(0.01)
                assert all("task" in node.tasks and "hash" in node.trajectories for node in judges)

                passing = [
                    {"core": True, "detail": True, "starts": True},
                    {"core": True, "detail": False, "starts": True},
                    {"core": False, "detail": False, "starts": True},
                ]
                for index, node in enumerate(judges):
                    criterion_results = {
                        item["id"]: {"passed": passing[index][item["id"]],
                                     "evidence": f"judge-{index} tested {item['id']}"}
                        for item in criteria
                    }
                    vote = sign_vote(wallets[index], node.trajectories["hash"],
                                     "PASS" if index == 0 else "FAIL",
                                     criteria_results=criterion_results)
                    assert node.add_signature(vote)

                for _ in range(200):
                    report = relay.tasks.get("task", {}).get("acceptance_score_report")
                    if report:
                        break
                    await asyncio.sleep(0.01)
                report = relay.tasks["task"]["acceptance_score_report"]
                assert report["criteria_score_percent"] == 70
                assert report["status"] == "FAILED"
                assert report["judge_agreement"]["detail"] == {"passed": 1, "failed": 2}
                assert "detail" in report["client_report_markdown"]
            finally:
                for node in judges:
                    for peer in list(node.peers):
                        await peer.close()
                for connection in connections:
                    connection.cancel()
                await asyncio.gather(*connections, return_exceptions=True)

    asyncio.run(scenario())
