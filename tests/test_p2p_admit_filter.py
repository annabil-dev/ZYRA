"""Gossip admission filter: canonical nodes drop unregistered ghost tasks."""

import asyncio

import pytest

from p2p.network import P2PNode
from p2p.protocol import MessageType, create_message, parse_message


def make_node(admit=None):
    node = P2PNode(port=5999, tracker_url="http://localhost:9")
    node.task_admit_filter = admit
    return node


def ghost(task_id="ghost-1"):
    return {"task_id": task_id, "status": "pending", "prompt": "x"}


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_no_filter_accepts_all_gossip():
    node = make_node()
    msg = parse_message(create_message(MessageType.NEW_TASK, ghost()))
    run(node.handle_message(msg, None, "raw"))
    assert "ghost-1" in node.tasks


def test_filter_drops_unknown_ghost_new_task():
    node = make_node(admit=lambda task_id, payload: False)
    msg = parse_message(create_message(MessageType.NEW_TASK, ghost()))
    run(node.handle_message(msg, None, "raw"))
    assert "ghost-1" not in node.tasks


def test_filter_admits_registered_task():
    node = make_node(admit=lambda task_id, payload: task_id == "real-1")
    run(node.handle_message(
        parse_message(create_message(MessageType.NEW_TASK, ghost("real-1"))),
        None, "raw"))
    assert "real-1" in node.tasks
    run(node.handle_message(
        parse_message(create_message(MessageType.NEW_TASK, ghost("ghost-1"))),
        None, "raw"))
    assert "ghost-1" not in node.tasks


def test_filter_raising_fails_open():
    def bad_filter(task_id, payload):
        raise RuntimeError("grpc down")

    node = make_node(admit=bad_filter)
    run(node.handle_message(
        parse_message(create_message(MessageType.NEW_TASK, ghost())),
        None, "raw"))
    assert "ghost-1" in node.tasks


def test_mempool_sync_filters_only_unknown_tasks():
    node = make_node(admit=lambda task_id, payload: task_id == "real-1")
    node.tasks["known-1"] = {"task_id": "known-1", "status": "pending"}
    payload = {"tasks": {
        "ghost-1": ghost(),
        "real-1": {"task_id": "real-1", "status": "pending"},
        "known-1": {"task_id": "known-1", "status": "mining"},
    }}
    run(node.handle_message(
        parse_message(create_message(MessageType.MEMPOOL_DATA, payload)),
        None, "raw"))
    assert "ghost-1" not in node.tasks
    assert "real-1" in node.tasks
    # Known-task updates bypass the filter so lease/vote flows keep working
    # (incoming mining/validating is normalized to pending by merge rules).
    assert "known-1" in node.tasks
    assert node.tasks["known-1"]["status"] == "pending"


def test_make_chain_admit_filter_without_config_returns_none(monkeypatch):
    from zyra_cmd import zyra_cli

    monkeypatch.setattr(zyra_cli.os, "environ", {})
    assert zyra_cli.make_chain_admit_filter() is None


def test_make_chain_admit_filter_caches_and_drops_ghosts(monkeypatch):
    from zyra_cmd import zyra_cli
    from zyra_cmd import mythchain_adapter

    calls = []

    class FakeAdapter:
        def __init__(self, config):
            pass

        def query_task(self, task_id):
            calls.append(task_id)
            return {"task_id": task_id} if task_id == "real-1" else None

    monkeypatch.setattr(mythchain_adapter, "MythchainTaskAdapter", FakeAdapter)
    monkeypatch.setattr(
        mythchain_adapter.MythchainConfig, "from_env",
        classmethod(lambda cls, role="miner", environ=None, **kwargs: object()),
    )
    admit = zyra_cli.make_chain_admit_filter(ttl_seconds=120)
    assert admit is not None
    assert admit("real-1", {}) is True
    assert admit("ghost-1", {}) is False
    # Cached: no further chain queries for repeated pushes.
    assert admit("real-1", {}) is True
    assert admit("ghost-1", {}) is False
    assert calls == ["real-1", "ghost-1"]
