from types import SimpleNamespace

import pytest

from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainError
from zyra_cmd.mythchain_balance import (
    parse_native_denom,
    parse_token_amount,
    validate_mythchain_address,
)
from zyra_cmd.mythchain_native import NativeMythchainClient, NativeMythchainQueryClient


def fake_config():
    from cosmpy.aerial.wallet import LocalWallet

    sender = LocalWallet.from_mnemonic(
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
        prefix="myth",
    )
    return MythchainConfig(
        chain_id="myth-testnet-1",
        address=str(sender.address()),
        timeout=3,
        fees="100umtc",
        gas_limit=250_000,
    )


class FakeSubmitted:
    def __init__(self, response):
        self.response = response
        self.wait_args = None

    def wait_to_complete(self, **kwargs):
        self.wait_args = kwargs
        return SimpleNamespace(response=self.response)


class FakeLedger:
    def __init__(self, response=None):
        self.submission = FakeSubmitted(response or SimpleNamespace(hash="ABC123", code=0, raw_log=""))
        self.calls = []

    def send_tokens(self, destination, amount, denom, sender, *, fee):
        self.calls.append(("send", str(destination), amount, denom, sender, fee))
        return self.submission

    def delegate_tokens(self, validator, amount, sender, *, fee):
        self.calls.append(("delegate", str(validator), amount, sender, fee))
        return self.submission

    def undelegate_tokens(self, validator, amount, sender, *, fee):
        self.calls.append(("undelegate", str(validator), amount, sender, fee))
        return self.submission


def client_with_fake_ledger(response=None):
    client = NativeMythchainClient.__new__(NativeMythchainClient)
    client.config = fake_config()
    from cosmpy.aerial.wallet import LocalWallet
    client.wallet = LocalWallet.from_mnemonic(
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
        prefix="myth",
    )
    client.ledger = FakeLedger(response)
    return client


def test_amount_parser_converts_human_tokens_to_exact_micro_units():
    assert parse_token_amount("1") == 1_000_000
    assert parse_token_amount("0.000001") == 1
    assert parse_token_amount("12.345678") == 12_345_678


@pytest.mark.parametrize("amount", ["0", "-1", "1.0000001", "1e2", "abc", ""])
def test_amount_parser_rejects_invalid_amounts(amount):
    with pytest.raises(MythchainError):
        parse_token_amount(amount)


def test_bank_send_uses_cosmos_denom_and_configured_fee():
    client = client_with_fake_ledger()
    from cosmpy.aerial.wallet import LocalWallet
    recipient = str(LocalWallet.from_mnemonic(
        "legal winner thank year wave sausage worth useful legal winner thank yellow",
        prefix="myth",
    ).address())
    result = client.send_bank_tokens(recipient, 2_500_000, "uzyra")

    call = client.ledger.calls[0]
    assert call[:4] == ("send", recipient, 2_500_000, "uzyra")
    assert call[4] is client.wallet
    assert call[5].gas_limit == 250_000
    assert str(call[5].amount["umtc"]) == "100umtc"
    assert result["txhash"] == "ABC123"


def test_delegate_and_undelegate_use_native_staking_ledger_methods():
    client = client_with_fake_ledger()
    from cosmpy.aerial.wallet import LocalWallet
    validator = str(LocalWallet.from_mnemonic(
        "legal winner thank year wave sausage worth useful legal winner thank yellow",
        prefix="mythvaloper",
    ).address())
    client.delegate_mtc(validator, 3_000_000)
    client.undelegate_mtc(validator, 1_000_000)

    assert client.ledger.calls[0][0:3] == ("delegate", validator, 3_000_000)
    assert client.ledger.calls[1][0:3] == ("undelegate", validator, 1_000_000)


def test_native_transaction_error_is_reported_instead_of_success():
    client = client_with_fake_ledger(SimpleNamespace(hash="BAD", code=5, raw_log="insufficient funds"))
    from cosmpy.aerial.wallet import LocalWallet
    recipient = str(LocalWallet.from_mnemonic(
        "legal winner thank year wave sausage worth useful legal winner thank yellow",
        prefix="myth",
    ).address())
    with pytest.raises(MythchainError, match="insufficient funds"):
        client.send_bank_tokens(recipient, 1_000_000, "umtc")


def test_native_denom_and_bech32_prefix_validation():
    assert parse_native_denom("MTC") == "umtc"
    assert parse_native_denom("uzyra") == "uzyra"
    with pytest.raises(MythchainError, match="Denom"):
        parse_native_denom("CELO")
    with pytest.raises(MythchainError, match="validator address"):
        validate_mythchain_address("myth1account", validator=True)


def test_query_staking_summary_maps_native_positions():
    from cosmpy.aerial.wallet import LocalWallet

    address = str(LocalWallet.from_mnemonic(
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
        prefix="myth",
    ).address())
    config = MythchainConfig(
        chain_id="myth-testnet-1", address=address,
        grpc_endpoint="grpc+http://127.0.0.1:9090",
    )

    class FakeSummaryLedger:
        def __init__(self, network, query_timeout_secs):
            pass

        def query_chain_id(self):
            return "myth-testnet-1"

        def query_bank_all_balances(self, address):
            return []

        def query_staking_summary(self, queried_address):
            assert str(queried_address) == address
            return SimpleNamespace(
                current_positions=[SimpleNamespace(
                    validator="mythvaloper1validator", amount=2_000_000, reward=12_345,
                )],
                unbonding_positions=[SimpleNamespace(
                    validator="mythvaloper1validator", amount=500_000,
                )],
            )

    query_client = NativeMythchainQueryClient(config, ledger_client_factory=FakeSummaryLedger)
    assert query_client.query_staking_summary() == {
        "delegations": [{
            "validator": "mythvaloper1validator", "amount_umtc": 2_000_000,
            "rewards_umtc": 12_345,
        }],
        "unbonding": [{"validator": "mythvaloper1validator", "amount_umtc": 500_000}],
    }
