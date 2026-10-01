"""Shared Client path for manual and synthetic task publication."""

from __future__ import annotations

import os
import uuid

from ai.execution.contract import contract_hash, validate_contract
from zyra_cmd.mythchain_adapter import TASK_CATEGORY_BASE_REWARDS, reward_category_for_task


def dispatch_client_task(prompt, acceptance, wallet, client_state, p2p_node, *, metadata=None):
    """Register, persist, and P2P-broadcast one task through the Client path."""
    metadata = dict(metadata or {})
    acceptance = validate_contract(acceptance)
    task_id = str(uuid.uuid4())
    acceptance_hash = contract_hash(acceptance)
    difficulty = metadata.get("difficulty", acceptance.get("difficulty"))
    profile = metadata.get("profile", acceptance.get("profile"))
    reward_category = reward_category_for_task(difficulty=difficulty, profile=profile)
    base_reward = TASK_CATEGORY_BASE_REWARDS[reward_category]
    chain_required = os.environ.get("ZYRA_MYTHCHAIN_MODE", "off").lower() == "required"

    if chain_required:
        from zyra_cmd.mythchain_adapter import MythchainConfig, MythchainTaskAdapter

        adapter = MythchainTaskAdapter(MythchainConfig.from_env("client"))
        adapter.register_task(
            task_id,
            acceptance_hash,
            criteria=acceptance.get("criteria"),
            difficulty=difficulty,
            profile=profile,
        )

    task_payload = {
        "task_id": task_id,
        "prompt": str(prompt),
        "reward": base_reward,
        "base_reward": base_reward,
        "reward_category": reward_category,
        "difficulty": difficulty,
        "status": "pending",
        "client": wallet.metamask_address or wallet.address,
        "acceptance": acceptance,
        "acceptance_hash": acceptance_hash,
        "lease_mode": "mythchain" if chain_required else "p2p-advisory",
        "origin": metadata.get("origin", "client"),
    }
    for key in ("synthetic_template_id", "synthetic_catalog_version", "synthetic_seed"):
        if metadata.get(key) is not None:
            task_payload[key] = metadata[key]

    saved_task = client_state.add_task(task_payload)
    p2p_node.add_task(task_payload)
    return task_payload, saved_task
