import json

from ai.execution.contract import make_contract
from zyra_cmd.task_dispatch import dispatch_client_task


class FakeWallet:
    address = "zyra-client-test"
    metamask_address = None


class FakeClientState:
    def __init__(self):
        self.tasks = []

    def get_task(self, task_id):
        for task in self.tasks:
            if task["task_id"] == task_id:
                return {"payload": json.dumps(task), "task_id": task_id}
        return None

    def add_task(self, task):
        self.tasks.append(task)
        return {"task_id": task["task_id"], "output_dir": "C:/ZYRA Results"}


class FakeP2PNode:
    def __init__(self):
        self.tasks = []

    def add_task(self, task):
        self.tasks.append(task)


def test_synthetic_dispatch_persists_and_broadcasts_through_client_path(monkeypatch):
    monkeypatch.setenv("ZYRA_MYTHCHAIN_MODE", "off")
    client_state = FakeClientState()
    p2p_node = FakeP2PNode()
    acceptance = make_contract("local dashboard task", web=True)
    metadata = {
        "origin": "synthetic",
        "difficulty": "hard",
        "profile": "flask-web",
        "synthetic_template_id": "flask-test-001",
        "synthetic_catalog_version": "synthetic-catalog-v2",
        "synthetic_seed": 1234,
    }

    task, saved = dispatch_client_task(
        "Create a synthetic test dashboard.", acceptance, FakeWallet(),
        client_state, p2p_node, metadata=metadata,
    )

    assert len(task["task_id"]) == 36
    assert task["origin"] == "synthetic"
    assert task["synthetic_template_id"] == "flask-test-001"
    assert task["reward_category"] == "heavy"
    assert task["base_reward"] == 0.5
    assert task["acceptance_hash"]
    assert saved["task_id"] == task["task_id"]
    assert client_state.tasks == [task]
    assert p2p_node.tasks == [task]
    assert task["lease_mode"] == "p2p-advisory"


def test_dispatch_registers_on_required_chain_before_p2p_broadcast(monkeypatch):
    import zyra_cmd.mythchain_adapter as adapter_module

    monkeypatch.setenv("ZYRA_MYTHCHAIN_MODE", "required")
    events = []

    class OrderedState(FakeClientState):
        def add_task(self, task):
            events.append("persist")
            return super().add_task(task)

    class OrderedP2P(FakeP2PNode):
        def add_task(self, task):
            events.append("broadcast")
            return super().add_task(task)

    class FakeAdapter:
        def register_task(self, task_id, acceptance_hash, **kwargs):
            events.append("chain-register")

    monkeypatch.setattr(adapter_module.MythchainConfig, "from_env", lambda role: role)
    monkeypatch.setattr(adapter_module, "MythchainTaskAdapter", lambda _config: FakeAdapter())

    task, _ = dispatch_client_task(
        "Run a local test task.", make_contract("local CLI task"), FakeWallet(),
        OrderedState(), OrderedP2P(), metadata={"origin": "synthetic", "profile": "python"},
    )

    assert events == ["chain-register", "persist", "broadcast"]
    assert task["lease_mode"] == "mythchain"


def test_dispatch_retries_same_task_id_without_duplicate_local_history(monkeypatch):
    monkeypatch.setenv("ZYRA_MYTHCHAIN_MODE", "off")
    state, p2p = FakeClientState(), FakeP2PNode()
    wallet = FakeWallet()
    acceptance = make_contract("retry safe local task")

    first, _ = dispatch_client_task(
        "Retry safe task", acceptance, wallet, state, p2p,
        task_id="stable-synthetic-id", metadata={"origin": "synthetic", "profile": "python"},
    )
    second, _ = dispatch_client_task(
        "Retry safe task", acceptance, wallet, state, p2p,
        task_id="stable-synthetic-id", metadata={"origin": "synthetic", "profile": "python"},
    )

    assert first["task_id"] == second["task_id"] == "stable-synthetic-id"
    assert len(state.tasks) == 1
    assert len(p2p.tasks) == 2
