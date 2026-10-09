import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "full_local_two_miner_test.py"
_SPEC = importlib.util.spec_from_file_location("full_local_two_miner_test", _SCRIPT_PATH)
_HARNESS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HARNESS)
from scripts.mythchain_smoke_guard import require_disposable_local_chain


def test_two_miner_harness_requires_explicit_testnet_opt_in(monkeypatch):
    monkeypatch.setenv("ZYRA_TEST_MYTHCHAIN", "0")
    with pytest.raises(SystemExit, match="disposable local-chain smoke test"):
        _HARNESS.main()


def test_two_miner_harness_accepts_only_expected_chain_and_loopback_endpoint():
    local = SimpleNamespace(
        signing_backend="native",
        chain_id="mythprotocol-3val-test",
        grpc_endpoint="grpc+http://127.0.0.1:9090",
    )
    _HARNESS._assert_disposable_local_config(local)

    with pytest.raises(RuntimeError, match="non-disposable chain ID"):
        _HARNESS._assert_disposable_local_config(SimpleNamespace(
            signing_backend="native", chain_id="myth-mainnet-1",
            grpc_endpoint="grpc+http://127.0.0.1:9090",
        ))
    with pytest.raises(RuntimeError, match="non-loopback"):
        _HARNESS._assert_disposable_local_config(SimpleNamespace(
            signing_backend="native", chain_id="mythprotocol-3val-test",
            grpc_endpoint="grpc+https://example.test:9090",
        ))


def test_two_miner_harness_rejects_legacy_signing_backend():
    with pytest.raises(RuntimeError, match="MYTHCHAIN_SIGNING_BACKEND=native"):
        _HARNESS._assert_disposable_local_config(SimpleNamespace(
            signing_backend="cli", chain_id="mythprotocol-3val-test",
            grpc_endpoint="grpc+http://127.0.0.1:9090",
        ))


def test_shared_smoke_guard_requires_explicit_opt_in_and_local_chain():
    config = SimpleNamespace(
        signing_backend="native",
        chain_id="mythprotocol-3val-test",
        grpc_endpoint="grpc+http://localhost:9090",
    )
    with pytest.raises(RuntimeError, match="ZYRA_TEST_MYTHCHAIN=1"):
        require_disposable_local_chain((config,), environ={})
    require_disposable_local_chain((config,), environ={"ZYRA_TEST_MYTHCHAIN": "1"})
    remote = SimpleNamespace(**{**config.__dict__, "grpc_endpoint": "grpc+https://rpc.example:9090"})
    with pytest.raises(RuntimeError, match="non-loopback"):
        require_disposable_local_chain((remote,), environ={"ZYRA_TEST_MYTHCHAIN": "1"})
