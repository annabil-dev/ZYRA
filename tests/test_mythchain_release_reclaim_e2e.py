"""Opt-in release/reclaim E2E against the disposable local 3-validator testnet."""

import asyncio
import dataclasses
import json
import os
import uuid
from urllib.parse import urlparse

import pytest

from ai.blockchain.wallet import ZyraWallet
from ai.execution.contract import contract_hash, make_contract
from p2p.network import P2PNode
from p2p.protocol import parse_message
from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainTaskAdapter
from zyra_cmd.zyra_cli import release_failed_miner_attempt


def test_failed_miner_releases_and_second_miner_reclaims_local_testnet(tmp_path):
    if os.environ.get("ZYRA_TEST_MYTHCHAIN") != "1":
        pytest.skip("Set ZYRA_TEST_MYTHCHAIN=1 to send transactions to the disposable local testnet")

    expected_chain_id = "mythprotocol-3val-test"
    if os.environ.get("MYTHCHAIN_CHAIN_ID") != expected_chain_id:
        pytest.fail(f"Refusing non-test chain; expected chain ID {expected_chain_id}")

    client_config = MythchainConfig.from_env("client")
    miner_a_config = MythchainConfig.from_env("miner")
    miner_b_config = dataclasses.replace(
        miner_a_config,
        key_name=os.environ["MYTHCHAIN_SECOND_MINER_KEY"],
        address=os.environ["MYTHCHAIN_SECOND_MINER_ADDRESS"],
        node=os.environ.get("MYTHCHAIN_SECOND_MINER_NODE", miner_a_config.node),
        home=os.environ.get("MYTHCHAIN_SECOND_MINER_HOME", miner_a_config.home),
    )
    configs = (client_config, miner_a_config, miner_b_config)
    for config in configs:
        if config.chain_id != expected_chain_id:
            pytest.fail(f"Refusing unexpected chain ID {config.chain_id}")
        if urlparse(config.node).hostname not in {"127.0.0.1", "localhost"}:
            pytest.fail(f"Refusing non-loopback RPC endpoint {config.node}")
    if miner_a_config.address == miner_b_config.address:
        pytest.fail("The two Miner service accounts must be distinct")

    acceptance = make_contract("Local-only smoke: prove an unused lease can be released and reclaimed.")
    acceptance_hash = contract_hash(acceptance)
    task_id = "release-reclaim-" + uuid.uuid4().hex
    client = MythchainTaskAdapter(client_config)
    miner_a = MythchainTaskAdapter(miner_a_config)
    miner_b = MythchainTaskAdapter(miner_b_config)
    client.register_task(task_id, acceptance_hash)

    chain_lease_a = miner_a.claim_task(task_id, acceptance_hash)
    assert chain_lease_a, "Miner A did not claim the fresh local test task"
    chain_attempt_a = chain_lease_a.get("attempt_id", chain_lease_a.get("attemptId"))

    p2p_task = {"task_id": task_id, "prompt": "local release/reclaim smoke",
                "status": "pending", "acceptance": acceptance,
                "acceptance_hash": acceptance_hash, "lease_mode": "mythchain"}
    p2p_a, p2p_b = P2PNode(), P2PNode()
    p2p_a.tasks[task_id] = dict(p2p_task)
    p2p_b.tasks[task_id] = dict(p2p_task)
    p2p_wallet_a = ZyraWallet(str(tmp_path / "p2p-miner-a"))
    p2p_wallet_b = ZyraWallet(str(tmp_path / "p2p-miner-b"))
    cleanup_attempt = chain_attempt_a
    cleanup_adapter = miner_a

    async def relay_release_and_reclaim():
        nonlocal cleanup_adapter, cleanup_attempt

        async def a_to_b(raw_message, exclude=None):
            await p2p_b.handle_message(parse_message(raw_message), None, raw_message)

        async def b_to_a(raw_message, exclude=None):
            await p2p_a.handle_message(parse_message(raw_message), None, raw_message)

        p2p_a.broadcast = a_to_b
        p2p_b.broadcast = b_to_a
        p2p_lease_a = p2p_a.claim_task(task_id, p2p_wallet_a)
        assert p2p_lease_a, "Miner A could not establish its local signed P2P lease"
        await asyncio.sleep(0)
        assert p2p_b.tasks[task_id]["lease"]["lease_id"] == p2p_lease_a["lease_id"]

        release = release_failed_miner_attempt(
            task_id, p2p_lease_a["lease_id"], chain_attempt_a, p2p_wallet_a, p2p_a,
            config_factory=lambda _role: miner_a_config,
            adapter_factory=lambda _config: miner_a,
        )
        assert release == {"chain_released": True, "p2p_released": True, "error": None}
        await asyncio.sleep(0.02)
        assert p2p_a.tasks[task_id]["status"] == "pending"
        assert p2p_b.tasks[task_id]["status"] == "pending"
        assert p2p_b.tasks[task_id].get("lease") is None

        released_state = miner_a.query_task(task_id)
        assert released_state["status"] == "RELEASED"
        assert released_state["attempt_id"] == chain_attempt_a

        new_lease = miner_b.claim_task(task_id, acceptance_hash)
        assert new_lease, "Miner B could not reclaim the released canonical lease"
        new_attempt = new_lease.get("attempt_id", new_lease.get("attemptId"))
        assert new_attempt != chain_attempt_a
        cleanup_adapter, cleanup_attempt = miner_b, new_attempt

        p2p_lease_b = p2p_b.claim_task(task_id, p2p_wallet_b)
        assert p2p_lease_b, "Miner B could not claim the released P2P task"
        await asyncio.sleep(0.02)
        assert p2p_a.tasks[task_id]["lease"]["miner_identity"] == p2p_wallet_b.signing_address

        states = [MythchainTaskAdapter(dataclasses.replace(client_config, node=node)).query_task(task_id)
                  for node in ("tcp://127.0.0.1:27657", "tcp://127.0.0.1:27654", "tcp://127.0.0.1:27651")]
        assert all(state and state.get("status") == "LEASED" for state in states)
        assert all(state.get("miner_address") == miner_b_config.address for state in states)
        assert all(state.get("attempt_id") == new_attempt for state in states)
        return new_attempt

    try:
        new_attempt = asyncio.run(relay_release_and_reclaim())
        print(json.dumps({"task_id": task_id, "released_attempt": chain_attempt_a,
                          "reclaimed_by": miner_b_config.address, "new_attempt": new_attempt,
                          "result": "PASS"}, indent=2))
    finally:
        current = cleanup_adapter.query_task(task_id)
        if (current and current.get("miner_address") == cleanup_adapter.config.address
                and current.get("attempt_id") == cleanup_attempt
                and str(current.get("status", "")).upper() == "LEASED"):
            cleanup_adapter.release_task(task_id, cleanup_attempt)
