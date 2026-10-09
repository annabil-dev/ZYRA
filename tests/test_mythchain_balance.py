from types import SimpleNamespace

import pytest
from cosmpy.aerial.wallet import LocalWallet

from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainError
from zyra_cmd.mythchain_balance import format_micro_units, query_wallet_balances, select_wallet_role
from zyra_cmd.mythchain_native import NativeMythchainQueryClient


MNEMONIC = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"


def query_env(address):
    return {
        "MYTHCHAIN_CHAIN_ID": "myth-testnet-1",
        "MYTHCHAIN_GRPC_ENDPOINT": "grpc+http://127.0.0.1:9090",
        "MYTHCHAIN_CLIENT_ADDRESS": address,
    }


def test_query_only_config_does_not_require_or_read_a_signing_key():
    address = str(LocalWallet.from_mnemonic(MNEMONIC, prefix="myth").address())
    config = MythchainConfig.from_env("client", environ=query_env(address), query_only=True)

    assert config.address == address
    assert config.chain_id == "myth-testnet-1"
    assert config.private_key_file == ""
    assert config.mnemonic_file == ""


def test_query_client_returns_native_bank_balances_without_a_key(monkeypatch):
    address = str(LocalWallet.from_mnemonic(MNEMONIC, prefix="myth").address())
    config = MythchainConfig.from_env("client", environ=query_env(address), query_only=True)

    class FakeLedger:
        def __init__(self, network, query_timeout_secs):
            assert network.chain_id == "myth-testnet-1"
            assert query_timeout_secs == config.timeout

        def query_chain_id(self):
            return "myth-testnet-1"

        def query_bank_all_balances(self, queried_address):
            assert str(queried_address) == address
            return [SimpleNamespace(denom="umtc", amount="1234567"),
                    SimpleNamespace(denom="uzyra", amount="2500000")]

    client = NativeMythchainQueryClient(config, ledger_client_factory=FakeLedger)
    assert client.query_bank_balances() == {"umtc": 1234567, "uzyra": 2500000}


def test_query_client_rejects_an_endpoint_on_a_different_chain():
    address = str(LocalWallet.from_mnemonic(MNEMONIC, prefix="myth").address())
    config = MythchainConfig.from_env("client", environ=query_env(address), query_only=True)

    class WrongChainLedger:
        def __init__(self, network, query_timeout_secs):
            pass

        def query_chain_id(self):
            return "different-chain"

    with pytest.raises(MythchainError, match="does not match endpoint chain ID"):
        NativeMythchainQueryClient(config, ledger_client_factory=WrongChainLedger)


def test_wallet_role_is_inferred_or_can_be_selected_explicitly():
    env = {"MYTHCHAIN_MINER_ADDRESS": "myth1miner"}
    assert select_wallet_role(env) == "miner"
    assert select_wallet_role(env, "judge") == "judge"
    with pytest.raises(MythchainError, match="MYTHCHAIN_WALLET_ROLE"):
        select_wallet_role(env, "validator")


def test_micro_denom_format_is_exact():
    assert format_micro_units(0) == "0.000000"
    assert format_micro_units(1_234_567) == "1.234567"
