"""Opt-in wallet transaction E2E against the loopback disposable Mythchain testnet."""

import os

import pytest

from zyra_cmd.mythchain_adapter import MythchainConfig
from zyra_cmd.mythchain_balance import validate_mythchain_address
from zyra_cmd.mythchain_native import NativeMythchainClient, NativeMythchainQueryClient
from scripts.mythchain_smoke_guard import EXPECTED_CHAIN_ID, require_disposable_local_chain


SMOKE_AMOUNT_UMTC = 1


def test_bank_send_and_mtc_delegate_undelegate_on_disposable_local_chain():
    if os.environ.get("ZYRA_TEST_MYTHCHAIN") != "1":
        pytest.skip("Set ZYRA_TEST_MYTHCHAIN=1 to send transactions to the disposable local testnet")

    from dotenv import load_dotenv
    load_dotenv()

    config = MythchainConfig.from_env("miner")
    # This test sends MTC and delegates/undelegates it. Refuse the active
    # myth-testnet-1 and any remotely hosted endpoint before constructing clients.
    require_disposable_local_chain((config,))

    recipient = os.environ.get("MYTHCHAIN_TEST_RECIPIENT_ADDRESS") or os.environ.get("MYTHCHAIN_MINER_ADDRESS", "")
    validator = os.environ.get("MYTHCHAIN_TEST_VALIDATOR_ADDRESS", "")
    if not recipient or not validator:
        pytest.skip("Set local MYTHCHAIN_TEST_RECIPIENT_ADDRESS and MYTHCHAIN_TEST_VALIDATOR_ADDRESS")
    recipient = validate_mythchain_address(recipient)
    validator = validate_mythchain_address(validator, validator=True)
    if recipient == config.address:
        pytest.fail("The test recipient must differ from the client signer")

    reader = NativeMythchainQueryClient(config)
    signer = NativeMythchainClient(config)

    recipient_before = reader.query_bank_balances(recipient).get("umtc", 0)
    signer.send_bank_tokens(recipient, SMOKE_AMOUNT_UMTC, "umtc")
    recipient_after = reader.query_bank_balances(recipient).get("umtc", 0)
    assert recipient_after == recipient_before + SMOKE_AMOUNT_UMTC

    before_staking = reader.query_staking_summary(config.address)
    delegated_before = sum(
        position["amount_umtc"] for position in before_staking["delegations"]
        if position["validator"] == validator
    )
    unbonding_before = sum(
        position["amount_umtc"] for position in before_staking["unbonding"]
        if position["validator"] == validator
    )

    signer.delegate_mtc(validator, SMOKE_AMOUNT_UMTC)
    after_delegate = reader.query_staking_summary(config.address)
    delegated_after = sum(
        position["amount_umtc"] for position in after_delegate["delegations"]
        if position["validator"] == validator
    )
    assert delegated_after == delegated_before + SMOKE_AMOUNT_UMTC

    signer.undelegate_mtc(validator, SMOKE_AMOUNT_UMTC)
    after_undelegate = reader.query_staking_summary(config.address)
    unbonding_after = sum(
        position["amount_umtc"] for position in after_undelegate["unbonding"]
        if position["validator"] == validator
    )
    assert unbonding_after >= unbonding_before + SMOKE_AMOUNT_UMTC
