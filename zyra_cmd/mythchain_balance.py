"""Public bank-balance queries for the configured Mythchain account."""

from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation

from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainError
from zyra_cmd.mythchain_native import NativeMythchainClient, NativeMythchainQueryClient


WALLET_ROLES = ("client", "miner", "judge")


def select_wallet_role(environ=None, role=None):
    env = os.environ if environ is None else environ
    selected = (role or env.get("MYTHCHAIN_WALLET_ROLE", "")).strip().lower()
    if selected:
        if selected not in WALLET_ROLES:
            raise MythchainError("MYTHCHAIN_WALLET_ROLE must be client, miner, or judge")
        return selected

    configured = [candidate for candidate in WALLET_ROLES
                  if env.get(f"MYTHCHAIN_{candidate.upper()}_ADDRESS")]
    if len(configured) == 1:
        return configured[0]
    if "client" in configured:
        return "client"
    return configured[0] if configured else "client"


def query_wallet_balances(environ=None, role=None, query_client_factory=None):
    selected_role, config, balances, _staking, _staking_error = query_wallet_state(
        environ=environ, role=role, query_client_factory=query_client_factory,
    )
    return selected_role, config, balances


def query_wallet_state(environ=None, role=None, query_client_factory=None):
    env = os.environ if environ is None else environ
    selected_role = select_wallet_role(env, role)
    config = MythchainConfig.from_env(selected_role, environ=env, query_only=True)
    client_factory = query_client_factory or NativeMythchainQueryClient
    client = client_factory(config)
    balances = client.query_bank_balances(config.address)
    try:
        staking = client.query_staking_summary(config.address)
        staking_error = None
    except Exception as exc:
        staking = None
        staking_error = str(exc)
    return selected_role, config, balances, staking, staking_error


def create_native_wallet_client(environ=None, role=None, client_factory=None):
    env = os.environ if environ is None else environ
    selected_role = select_wallet_role(env, role)
    config = MythchainConfig.from_env(selected_role, environ=env)
    if config.signing_backend != "native":
        raise MythchainError("Native wallet transactions require MYTHCHAIN_SIGNING_BACKEND=native")
    factory = client_factory or NativeMythchainClient
    return selected_role, config, factory(config)


def parse_token_amount(amount):
    text = str(amount).strip()
    if not re.fullmatch(r"(?:\d+(?:\.\d{1,6})?|\.\d{1,6})", text):
        raise MythchainError("Amount must be a positive number with at most 6 decimal places")
    try:
        base_units = Decimal(text) * Decimal(1_000_000)
    except InvalidOperation as exc:
        raise MythchainError("Invalid token amount") from exc
    if base_units <= 0 or base_units != base_units.to_integral_value():
        raise MythchainError("Amount must be positive and use at most 6 decimal places")
    return int(base_units)


def parse_native_denom(denom):
    selected = str(denom).strip().lower()
    denoms = {"mtc": "umtc", "umtc": "umtc", "zyra": "uzyra", "uzyra": "uzyra"}
    if selected not in denoms:
        raise MythchainError("Denom must be MTC/umtc or ZYRA/uzyra")
    return denoms[selected]


def validate_mythchain_address(address, *, validator=False):
    expected_prefix = "mythvaloper1" if validator else "myth1"
    if not isinstance(address, str) or not address.startswith(expected_prefix):
        kind = "validator" if validator else "account"
        raise MythchainError(f"Enter a valid {kind} address beginning with {expected_prefix}")
    try:
        from cosmpy.crypto.address import Address
        Address(address)
    except Exception as exc:
        raise MythchainError("Address is not a valid Mythchain bech32 address") from exc
    return address


def format_micro_units(amount):
    amount = int(amount)
    whole, fractional = divmod(amount, 1_000_000)
    return f"{whole}.{fractional:06d}"
