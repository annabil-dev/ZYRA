import json
import subprocess
from types import SimpleNamespace

import pytest

from zyra_cmd.mythchain_adapter import (MythchainConfig, MythchainError,
                                        MythchainTaskAdapter, MythchainUnavailable)


def config():
    return MythchainConfig(binary="mythprotocold", node="http://127.0.0.1:26657",
                           chain_id="mythprotocol", key_name="miner", address="myth1miner",
                           lease_blocks=100, timeout=2)


def result(payload, code=0, stderr=""):
    return SimpleNamespace(returncode=code, stdout=json.dumps(payload), stderr=stderr)


def test_two_competing_miners_only_canonical_owner_gets_lease():
    task = {"task_id": "job", "acceptance_hash": "a" * 64, "status": "OPEN"}
    canonical = {"task_id": "job", "acceptance_hash": "a" * 64,
                 "miner_address": "myth1winner", "attempt_id": "b" * 64,
                 "status": "LEASED", "expires_at_height": 500}

    def loser_runner(command, **kwargs):
        if "status" in command:
            return result({"sync_info": {"latest_block_height": "400"}})
        return result({"found": True, "lease": canonical})

    loser = MythchainTaskAdapter(
        MythchainConfig(**{**config().__dict__, "address": "myth1loser"}), runner=loser_runner)
    assert loser.claim_task("job", "a" * 64) is None

    calls = []
    query_responses = [result({"found": True, "lease": task}), result({"found": True, "lease": canonical})]
    status_responses = [result({"sync_info": {"latest_block_height": "400"}}),
                        result({"sync_info": {"latest_block_height": "401"}})]

    def winner_runner(command, **kwargs):
        calls.append(command)
        if "claim-task" in command:
            return result({"txhash": "committed"})
        if "status" in command:
            return status_responses.pop(0)
        return query_responses.pop(0)

    winner = MythchainTaskAdapter(
        MythchainConfig(**{**config().__dict__, "address": "myth1winner"}),
        runner=winner_runner, sleep=lambda _: None)
    assert winner.claim_task("job", "a" * 64)["attempt_id"] == "b" * 64
    tx = next(command for command in calls if "claim-task" in command)
    assert "--task-id" in tx and "job" in tx
    assert "--broadcast-mode" in tx and "sync" in tx
    assert "--yes" in tx


def test_claim_does_not_treat_tx_success_as_proof_without_canonical_query():
    open_task = {"task_id": "job", "acceptance_hash": "a" * 64, "status": "OPEN"}
    foreign_lease = {"task_id": "job", "acceptance_hash": "a" * 64,
                     "miner_address": "myth1other", "attempt_id": "b" * 64,
                     "status": "LEASED", "expires_at_height": 100}
    query_responses = [result({"found": True, "lease": open_task}), result({"found": True, "lease": foreign_lease})]
    status_responses = [result({"sync_info": {"latest_block_height": "10"}}),
                        result({"sync_info": {"latest_block_height": "11"}})]

    def runner(command, **kwargs):
        if "claim-task" in command:
            return result({"txhash": "in-mempool"})
        if "status" in command:
            return status_responses.pop(0)
        return query_responses.pop(0)

    adapter = MythchainTaskAdapter(config(), runner=runner, sleep=lambda _: None)
    assert adapter.claim_task("job", "a" * 64) is None


def test_release_task_confirms_canonical_released_state():
    leased = {"task_id": "job", "acceptance_hash": "a" * 64, "miner_address": "myth1miner",
              "attempt_id": "b" * 64, "status": "LEASED", "expires_at_height": "500"}
    released = {**leased, "status": "RELEASED", "expires_at_height": "420"}
    queries = [leased, released]
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        if "release-task" in command:
            return result({"txhash": "release-tx"})
        return result({"found": True, "lease": queries.pop(0)})

    adapter = MythchainTaskAdapter(config(), runner=runner, sleep=lambda _: None)
    result_state = adapter.release_task("job", "b" * 64)

    assert result_state["status"] == "RELEASED"
    tx = next(command for command in commands if "release-task" in command)
    assert "--task-id" in tx and tx[tx.index("--task-id") + 1] == "job"
    assert "--attempt-id" in tx and tx[tx.index("--attempt-id") + 1] == "b" * 64


def test_release_task_rejects_foreign_or_submitted_attempt():
    lease = {"task_id": "job", "acceptance_hash": "a" * 64, "miner_address": "myth1other",
             "attempt_id": "b" * 64, "status": "LEASED", "expires_at_height": "500"}
    adapter = MythchainTaskAdapter(config(), runner=lambda *args, **kwargs: result({"found": True, "lease": lease}))
    with pytest.raises(MythchainError, match="does not own"):
        adapter.release_task("job", "b" * 64)


def test_acceptance_hash_mismatch_is_hard_failure():
    response = {"found": True, "lease": {"task_id": "job", "acceptance_hash": "c" * 64,
                                             "status": "OPEN"}}
    adapter = MythchainTaskAdapter(config(), runner=lambda *args, **kwargs: result(response))
    with pytest.raises(MythchainError, match="acceptance hash"):
        adapter.claim_task("job", "a" * 64)


def test_unavailable_cli_fails_closed():
    def runner(*args, **kwargs):
        raise FileNotFoundError("mythprotocold")

    adapter = MythchainTaskAdapter(config(), runner=runner)
    with pytest.raises(MythchainUnavailable):
        adapter.claim_task("job", "a" * 64)


def test_cli_timeout_is_reported_as_unavailable():
    def runner(*args, **kwargs):
        raise subprocess.TimeoutExpired("mythprotocold", 2)

    adapter = MythchainTaskAdapter(config(), runner=runner)
    with pytest.raises(MythchainUnavailable):
        adapter.query_task("job")


def test_rpc_connection_refused_is_reported_as_unavailable():
    failed = SimpleNamespace(returncode=1, stdout="",
                             stderr='post failed: dial tcp 127.0.0.1:26657: connect: connection refused')
    adapter = MythchainTaskAdapter(config(), runner=lambda *args, **kwargs: failed)
    with pytest.raises(MythchainUnavailable, match="RPC unavailable"):
        adapter.query_task("job")


def test_role_configuration_requires_explicit_cosmos_key_and_address():
    with pytest.raises(MythchainError, match="MYTHCHAIN_MINER_KEY"):
        MythchainConfig.from_env("miner", environ={})


def test_role_specific_node_and_home_override_shared_defaults():
    env = {"MYTHCHAIN_MINER_KEY": "miner", "MYTHCHAIN_MINER_ADDRESS": "myth1miner",
           "MYTHCHAIN_NODE": "tcp://shared:26657", "MYTHCHAIN_HOME": "/shared/home",
           "MYTHCHAIN_MINER_NODE": "tcp://miner-validator:26657",
           "MYTHCHAIN_MINER_HOME": "/miner/home"}
    config = MythchainConfig.from_env("miner", environ=env)
    assert config.node == "tcp://miner-validator:26657"
    assert config.home == "/miner/home"


def test_task_reward_category_maps_difficulty_and_profile_deterministically():
    from zyra_cmd.mythchain_adapter import reward_category_for_task

    assert reward_category_for_task(difficulty="easy", profile="flask-web") == "light"
    assert reward_category_for_task(difficulty="hard") == "heavy"
    assert reward_category_for_task(difficulty="very_hard") == "very_heavy"
    assert reward_category_for_task(profile="python") == "light"
    assert reward_category_for_task(profile="flask-web") == "medium"
    with pytest.raises(MythchainError, match="Unsupported task difficulty"):
        reward_category_for_task(difficulty="impossible", profile="python")


@pytest.mark.parametrize("rejection", [
    result({}, code=1, stderr="gas fee required: gasless bootstrap is used or complete"),
    result({"code": 1, "raw_log": "gas fee required: gasless bootstrap is complete"}),
])
def test_transactions_retry_with_uzyra_fees_only_after_gasless_rejection(rejection):
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        if "--fees" in command:
            return result({"txhash": "paid-tx"})
        return rejection

    adapter = MythchainTaskAdapter(
        MythchainConfig(**{**config().__dict__, "fees": "20uzyra"}), runner=runner)
    response = adapter._run(["tx", "mythprotocol", "claim-task"], tx=True)

    assert response["txhash"] == "paid-tx"
    assert len(commands) == 2
    assert "--fees" not in commands[0]
    assert commands[1][commands[1].index("--fees") + 1] == "20uzyra"


def test_successful_gasless_transaction_does_not_attach_configured_fees():
    commands = []
    adapter = MythchainTaskAdapter(
        MythchainConfig(**{**config().__dict__, "fees": "20uzyra"}),
        runner=lambda command, **kwargs: (commands.append(command) or result({"txhash": "free-tx"})),
    )

    response = adapter._run(["tx", "mythprotocol", "claim-task"], tx=True)

    assert response["txhash"] == "free-tx"
    assert len(commands) == 1
    assert "--fees" not in commands[0]


def test_register_task_commits_weighted_criteria_with_acceptance_hash():
    criteria = [{"id": "runs", "description": "App runs", "weight": 100,
                 "hard_gate": True, "check": {"type": "application_runs"}}]
    chain_criteria = json.dumps(criteria, separators=(",", ":"))
    lease = {"task_id": "weighted", "acceptance_hash": "a" * 64,
             "task_category": "light",
             "criteria_json": chain_criteria, "status": "OPEN"}
    queries = [None, lease]
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        if "register-task" in command:
            return result({"txhash": "register-tx"})
        lease = queries.pop(0)
        return result({"found": lease is not None, "lease": lease})

    adapter = MythchainTaskAdapter(config(), runner=runner, sleep=lambda _: None)
    registered = adapter.register_task("weighted", "a" * 64, criteria=criteria, profile="python")

    assert json.loads(registered["criteria_json"]) == criteria
    tx = next(command for command in commands if "register-task" in command)
    assert "--criteria-json" in tx
    assert json.loads(tx[tx.index("--criteria-json") + 1]) == criteria
    assert tx[tx.index("--task-category") + 1] == "light"


def test_weighted_judge_vote_sends_results_and_confirms_canonical_score():
    criteria = [{"id": "runs", "description": "App runs", "weight": 100,
                 "hard_gate": True, "check": {"type": "application_runs"}}]
    criteria_json = json.dumps(criteria, sort_keys=True, separators=(",", ":"))
    results = {"runs": {"passed": True, "evidence": "App exited successfully"}}
    result_json = json.dumps(results, sort_keys=True, separators=(",", ":"))
    submitted = {"task_id": "job", "acceptance_hash": "a" * 64,
                 "criteria_json": criteria_json, "miner_address": "myth1miner",
                 "attempt_id": "b" * 64, "expires_at_height": "500", "status": "SUBMITTED",
                 "result_cid": "sha256:" + "c" * 64, "votes": []}
    voted = {**submitted, "status": "APPROVED", "criteria_score_numerator": "100",
             "criteria_score_denominator": "100", "votes": [{
                 "judge_address": "myth1judge", "attempt_id": "b" * 64, "verdict": "PASS",
                 "reason": "criteria passed", "criteria_results_json": result_json,
             }]}
    queries = [submitted, voted]
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        if "status" in command:
            return result({"sync_info": {"latest_block_height": "120"}})
        if "vote-task" in command:
            return result({"txhash": "weighted-vote-tx"})
        return result({"found": True, "lease": queries.pop(0)})

    state = MythchainTaskAdapter(
        MythchainConfig(**{**config().__dict__, "address": "myth1judge"}),
        runner=runner, sleep=lambda _: None,
    ).vote_task("job", "b" * 64, "PASS", "criteria passed", acceptance_hash="a" * 64,
                result_cid="sha256:" + "c" * 64, criteria_results=results, criteria=criteria)

    assert state["status"] == "APPROVED"
    assert state["criteria_score_numerator"] == "100"
    tx = next(command for command in commands if "vote-task" in command)
    assert "--criteria-results-json" in tx
    assert json.loads(tx[tx.index("--criteria-results-json") + 1]) == results


def test_weighted_vote_refuses_verdict_that_disagrees_with_judge_score():
    criteria = [{"id": "runs", "description": "App runs", "weight": 100,
                 "hard_gate": True, "check": {"type": "application_runs"}}]
    lease = {"task_id": "job", "acceptance_hash": "a" * 64,
             "criteria_json": json.dumps(criteria), "attempt_id": "b" * 64,
             "expires_at_height": "500", "status": "SUBMITTED", "votes": []}
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        if "status" in command:
            return result({"sync_info": {"latest_block_height": "120"}})
        return result({"found": True, "lease": lease})

    adapter = MythchainTaskAdapter(config(), runner=runner)
    with pytest.raises(MythchainError, match="does not match"):
        adapter.vote_task("job", "b" * 64, "FAIL", criteria_results={
            "runs": {"passed": True, "evidence": "App runs"},
        })
    assert not any("vote-task" in command for command in commands)


def test_wsl_execution_wraps_daemon_command_for_windows_miners():
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return result({"found": False})

    adapter = MythchainTaskAdapter(
        MythchainConfig(**{**config().__dict__, "binary": "/home/test/mythprotocold",
                           "wsl_distro": "Ubuntu"}), runner=runner)
    assert adapter.query_task("job") is None
    assert calls[0][:5] == ["wsl.exe", "-d", "Ubuntu", "--", "/home/test/mythprotocold"]


def test_submit_result_waits_for_canonical_submitted_state():
    active = {"task_id": "job", "acceptance_hash": "a" * 64,
              "miner_address": "myth1miner", "attempt_id": "b" * 64,
              "expires_at_height": "500", "status": "LEASED"}
    submitted = {**active, "status": "SUBMITTED", "result_cid": "sha256:" + "c" * 64,
                 "proof_hash": "d" * 64, "votes": []}
    queries = [result({"found": True, "lease": active}),
               result({"found": True, "lease": submitted})]
    statuses = [result({"sync_info": {"latest_block_height": "400"}})]
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        if "status" in command:
            return statuses.pop(0)
        if "submit-task-result" in command:
            return result({"txhash": "result-tx"})
        return queries.pop(0)

    adapter = MythchainTaskAdapter(config(), runner=runner, sleep=lambda _: None)
    committed = adapter.submit_task_result("job", "b" * 64, "sha256:" + "c" * 64, "d" * 64)
    assert committed["status"] == "SUBMITTED"
    tx = next(command for command in commands if "submit-task-result" in command)
    assert "--attempt-id" in tx and "--result-cid" in tx and "--proof-hash" in tx


def test_submit_result_rejects_stale_attempt_before_tx():
    lease = {"task_id": "job", "acceptance_hash": "a" * 64,
             "miner_address": "myth1miner", "attempt_id": "b" * 64,
             "expires_at_height": "500", "status": "LEASED"}
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if "status" in command:
            return result({"sync_info": {"latest_block_height": "100"}})
        return result({"found": True, "lease": lease})

    adapter = MythchainTaskAdapter(config(), runner=runner)
    with pytest.raises(MythchainError, match="attempt"):
        adapter.submit_task_result("job", "e" * 64, "sha256:" + "c" * 64, "d" * 64)
    assert not any("submit-task-result" in command for command in calls)


def test_judge_vote_waits_for_its_canonical_vote_and_quorum_status():
    submitted = {"task_id": "job", "acceptance_hash": "a" * 64,
                 "miner_address": "myth1miner", "attempt_id": "b" * 64,
                 "expires_at_height": "500", "status": "SUBMITTED",
                 "result_cid": "sha256:" + "c" * 64, "proof_hash": "d" * 64, "votes": []}
    voted = {**submitted, "status": "APPROVED", "votes": [
        {"judge_address": "myth1judge", "attempt_id": "b" * 64, "verdict": "PASS",
         "reason": "acceptance checks passed", "height": "120"},
        {"judge_address": "myth1otherjudge", "attempt_id": "b" * 64, "verdict": "PASS",
         "reason": "all good", "height": "121"},
    ]}
    queries = [result({"found": True, "lease": submitted}), result({"found": True, "lease": voted})]
    statuses = [result({"sync_info": {"latest_block_height": "110"}})]
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        if "status" in command:
            return statuses.pop(0)
        if "vote-task" in command:
            return result({"txhash": "vote-tx"})
        return queries.pop(0)

    judge_config = MythchainConfig(**{**config().__dict__, "address": "myth1judge"})
    state = MythchainTaskAdapter(judge_config, runner=runner, sleep=lambda _: None).vote_task(
        "job", "b" * 64, "PASS", "acceptance checks passed", acceptance_hash="a" * 64,
        result_cid="sha256:" + "c" * 64)
    assert state["status"] == "APPROVED"
    tx = next(command for command in commands if "vote-task" in command)
    assert "--verdict" in tx and "PASS" in tx and "--reason" in tx


def test_judge_cannot_vote_on_stale_attempt():
    submitted = {"task_id": "job", "acceptance_hash": "a" * 64,
                 "miner_address": "myth1miner", "attempt_id": "b" * 64,
                 "expires_at_height": "500", "status": "SUBMITTED", "votes": []}
    adapter = MythchainTaskAdapter(config(), runner=lambda command, **kwargs: result(
        {"found": True, "lease": submitted}))
    with pytest.raises(MythchainError, match="attempt_id"):
        adapter.vote_task("job", "e" * 64, "PASS")
