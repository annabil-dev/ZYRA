import json
from datetime import datetime, timezone

from zyra_cmd.synthetic_producer import ProducerStore, SyntheticTaskProducer


class FakeClientState:
    def __init__(self):
        self.tasks = []

    def get_task(self, task_id):
        for task in self.tasks:
            if task["task_id"] == task_id:
                return {"payload": json.dumps(task), "task_id": task_id}
        return None

    def add_task(self, payload):
        self.tasks.append(payload)
        return {"task_id": payload["task_id"], "output_dir": "/tmp/zyra-results"}

    def list_tasks(self):
        return [{"payload": json.dumps(task), "status": task["status"]} for task in self.tasks]

    def update_from_network(self, payload):
        return None


class FakeP2PNode:
    def __init__(self):
        self.tasks = []

    def add_task(self, payload):
        self.tasks.append(payload)


class FakeWallet:
    address = "zyra-producer-evm"
    metamask_address = None


def test_producer_publishes_one_task_persists_quota_and_keeps_the_rest_queued(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYRA_MYTHCHAIN_MODE", "off")
    store_path = tmp_path / "producer.sqlite3"
    store = ProducerStore(store_path)
    state, p2p = FakeClientState(), FakeP2PNode()
    producer = SyntheticTaskProducer(
        client_state=state, p2p_node=p2p, wallet=FakeWallet(), store=store,
        max_per_day=50, min_interval=300, max_interval=1800, seed=22, on_event=lambda _msg: None,
    )

    assert producer.submit_one()
    assert store.submitted_today(datetime.now(timezone.utc).date().isoformat()) == 1
    assert store.queued_count() == 23
    assert len(state.tasks) == len(p2p.tasks) == 1
    assert state.tasks[0]["origin"] == "synthetic"
    assert state.tasks[0]["synthetic_template_id"]
    assert store.next_due_at() is not None

    restarted_store = ProducerStore(store_path)
    assert restarted_store.queued_count() == 23
    assert restarted_store.submitted_today(datetime.now(timezone.utc).date().isoformat()) == 1


def test_producer_enforces_daily_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYRA_MYTHCHAIN_MODE", "off")
    store = ProducerStore(tmp_path / "producer.sqlite3")
    producer = SyntheticTaskProducer(
        client_state=FakeClientState(), p2p_node=FakeP2PNode(), wallet=FakeWallet(), store=store,
        max_per_day=1, min_interval=300, max_interval=1800, seed=7, on_event=lambda _msg: None,
    )

    assert producer.submit_one()
    assert not producer.submit_one()
    assert store.submitted_today(datetime.now(timezone.utc).date().isoformat()) == 1


def test_producer_restores_only_pending_synthetic_tasks(tmp_path):
    state, p2p = FakeClientState(), FakeP2PNode()
    state.tasks.extend([
        {"task_id": "synthetic-1", "origin": "synthetic", "status": "pending"},
        {"task_id": "manual-1", "origin": "client", "status": "pending"},
        {"task_id": "synthetic-done", "origin": "synthetic", "status": "completed"},
    ])
    restored = ProducerStore(tmp_path / "producer.sqlite3").restore_pending_tasks(state, p2p)
    assert restored == 1
    assert [task["task_id"] for task in p2p.tasks] == ["synthetic-1"]
