"""Opt-in adapter for canonical Mythchain task registration and miner claims.

This adapter deliberately uses the Mythchain CLI as the signing boundary. It
does not read or handle Cosmos private keys itself.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


class MythchainError(RuntimeError):
    pass


class MythchainUnavailable(MythchainError):
    pass


TASK_CATEGORY_BASE_REWARDS = {
    "light": 0.10,
    "medium": 0.25,
    "heavy": 0.50,
    "very_heavy": 1.00,
}


def reward_category_for_task(difficulty=None, profile=None):
    """Map task difficulty to its fixed reward category, using runtime profile as fallback."""
    difficulty_map = {
        "easy": "light", "light": "light", "low": "light", "simple": "light",
        "medium": "medium", "normal": "medium", "moderate": "medium",
        "hard": "heavy", "heavy": "heavy", "high": "heavy", "advanced": "heavy",
        "very_hard": "very_heavy", "very-hard": "very_heavy",
        "very-heavy": "very_heavy", "very_heavy": "very_heavy",
        "expert": "very_heavy",
    }
    profile_map = {"python": "light", "flask-web": "medium"}
    if difficulty is not None:
        normalized = str(difficulty).strip().lower().replace(" ", "_")
        category = difficulty_map.get(normalized)
        if category is None:
            raise MythchainError(f"Unsupported task difficulty for reward category: {difficulty!r}")
        return category
    normalized_profile = str(profile or "").strip().lower()
    category = profile_map.get(normalized_profile)
    if category is None:
        raise MythchainError("Task reward category requires a known difficulty or runtime profile")
    return category


def _canonical_criteria_json(criteria):
    if criteria is None:
        return ""
    from ai.execution.scoring import validate_criteria
    normalized = validate_criteria(criteria)
    if any("check" not in criterion for criterion in normalized):
        raise MythchainError("Every on-chain weighted criterion needs a machine-executable check")
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > 256 * 1024:
        raise MythchainError("Weighted criteria JSON exceeds the 256 KiB chain limit")
    return encoded


def _state_criteria_json(lease):
    raw = lease.get("criteria_json", lease.get("criteriaJson", ""))
    if not raw:
        return ""
    try:
        return _canonical_criteria_json(json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MythchainError("Mythchain returned invalid weighted criteria JSON") from exc


def _canonical_criteria_results_json(criteria_json, results):
    if not isinstance(results, dict):
        raise MythchainError("Weighted judge votes require per-criterion results")
    try:
        from ai.execution.scoring import score_acceptance
        criteria = json.loads(criteria_json)
        score = score_acceptance(criteria, results)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MythchainError(f"Invalid weighted judge results: {exc}") from exc
    encoded = json.dumps(results, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > 256 * 1024:
        raise MythchainError("Weighted criterion results exceed the 256 KiB chain limit")
    return encoded, score


@dataclass(frozen=True)
class MythchainConfig:
    binary: str
    node: str
    chain_id: str
    key_name: str
    address: str
    lease_blocks: int = 500
    timeout: int = 90
    fees: str = ""
    keyring_backend: str = "os"
    home: str = ""
    wsl_distro: str = ""
    keyring_password: str = ""

    @classmethod
    def from_env(cls, role="miner", environ=None):
        env = os.environ if environ is None else environ
        role = role.upper()
        required = {
            "binary": env.get("MYTHCHAIN_BINARY", "mythprotocold"),
            "node": env.get(f"MYTHCHAIN_{role}_NODE",
                            env.get("MYTHCHAIN_NODE", "tcp://127.0.0.1:26657")),
            "chain_id": env.get("MYTHCHAIN_CHAIN_ID", "mythprotocol"),
            "key_name": env.get(f"MYTHCHAIN_{role}_KEY", ""),
            "address": env.get(f"MYTHCHAIN_{role}_ADDRESS", ""),
        }
        missing = [name for name in ("key_name", "address") if not required[name]]
        if missing:
            raise MythchainError(f"Missing MYTHCHAIN_{role}_KEY / MYTHCHAIN_{role}_ADDRESS configuration")
        try:
            lease_blocks = int(env.get("MYTHCHAIN_LEASE_BLOCKS", "500"))
            timeout = int(env.get("MYTHCHAIN_COMMAND_TIMEOUT", "90"))
        except ValueError as exc:
            raise MythchainError("Mythchain lease blocks and command timeout must be integers") from exc
        if not 1 <= lease_blocks <= 10_000 or timeout < 1:
            raise MythchainError("MYTHCHAIN_LEASE_BLOCKS must be 1..10000 and timeout must be positive")
        keyring_password = env.get("MYTHCHAIN_KEYRING_PASSWORD", "")
        password_file = env.get("MYTHCHAIN_KEYRING_PASSWORD_FILE", "")
        if password_file:
            try:
                keyring_password = Path(password_file).read_text(encoding="utf-8").rstrip("\r\n")
            except OSError as exc:
                raise MythchainError("Could not read MYTHCHAIN_KEYRING_PASSWORD_FILE") from exc
        return cls(**required, lease_blocks=lease_blocks, timeout=timeout,
                   fees=env.get("MYTHCHAIN_TX_FEES", ""),
                   keyring_backend=env.get("MYTHCHAIN_KEYRING_BACKEND", "os"),
                   home=env.get(f"MYTHCHAIN_{role}_HOME", env.get("MYTHCHAIN_HOME", "")),
                   wsl_distro=env.get("MYTHCHAIN_WSL_DISTRO", ""),
                   keyring_password=keyring_password)


class MythchainTaskAdapter:
    def __init__(self, config, runner=None, sleep=time.sleep):
        self.config = config
        self.runner = runner or subprocess.run
        self.sleep = sleep

    def _run(self, args, *, tx=False):
        command = [self.config.binary, *args, "--node", self.config.node, "--output", "json"]
        if self.config.home:
            command.extend(["--home", self.config.home])
        commands = [command]
        if tx:
            command.extend(["--from", self.config.key_name, "--chain-id", self.config.chain_id,
                            "--broadcast-mode", "sync", "--yes", "--gas", "1000000",
                            "--keyring-backend", self.config.keyring_backend])
            if self.config.fees:
                commands.append(command + ["--fees", self.config.fees])

        for index, command in enumerate(commands):
            if self.config.wsl_distro:
                command = [os.environ.get("WSL_BINARY", "wsl.exe"), "-d", self.config.wsl_distro,
                           "--", *command]
            try:
                run_options = {"capture_output": True, "text": True,
                               "timeout": self.config.timeout, "check": False}
                if tx and self.config.keyring_password:
                    run_options["input"] = self.config.keyring_password + "\n"
                result = self.runner(command, **run_options)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise MythchainUnavailable(f"Mythchain CLI/RPC unavailable: {exc}") from exc
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "command failed").strip()[-2000:]
                if index == 0 and len(commands) > 1 and self._is_fee_rejection(detail):
                    continue
                transport_failures = ("connection refused", "connection reset", "network is unreachable",
                                      "no such host", "context deadline exceeded", "i/o timeout",
                                      "failed to connect", "connection timed out")
                if any(marker in detail.lower() for marker in transport_failures):
                    raise MythchainUnavailable(f"Mythchain RPC unavailable: {detail}")
                raise MythchainError(f"Mythchain command failed ({result.returncode}): {detail}")
            try:
                response = json.loads(result.stdout)
            except (TypeError, json.JSONDecodeError) as exc:
                raise MythchainError("Mythchain CLI did not return valid JSON (--output json)") from exc
            if tx and isinstance(response, dict):
                try:
                    code = int(response.get("code", 0))
                except (TypeError, ValueError) as exc:
                    raise MythchainError("Malformed Mythchain transaction response") from exc
                if code:
                    detail = response.get("raw_log", response.get("rawLog", "transaction failed"))
                    if index == 0 and len(commands) > 1 and self._is_fee_rejection(str(detail)):
                        continue
                    raise MythchainError(f"Mythchain transaction failed ({code}): {detail}")
            return response
        raise MythchainError("Mythchain transaction could not be submitted")

    @staticmethod
    def _is_fee_rejection(detail):
        lowered = str(detail).lower()
        return any(marker in lowered for marker in (
            "gas fee required", "insufficient fees", "insufficient fee", "gasless bootstrap",
        ))

    @staticmethod
    def _lease(response):
        if not isinstance(response, dict):
            raise MythchainError("Unexpected Mythchain task query response")
        lease = response.get("lease", response.get("task"))
        if lease is None and "task_id" in response:
            lease = response
        if lease is not None and not isinstance(lease, dict):
            raise MythchainError("Malformed lease in Mythchain response")
        return lease

    @staticmethod
    def _value(record, snake_name, camel_name=None, default=None):
        return record.get(snake_name, record.get(camel_name or snake_name, default))

    @staticmethod
    def _votes(lease):
        votes = lease.get("votes", [])
        if not isinstance(votes, list):
            raise MythchainError("Malformed votes list in Mythchain task state")
        return votes

    def _check_committed_tx(self, tx_hash):
        if not tx_hash:
            return None
        try:
            response = self._run(["query", "tx", tx_hash])
        except MythchainError as exc:
            if "not found" in str(exc).lower():
                return None
            raise
        try:
            code = int(response.get("code", 0))
        except (AttributeError, TypeError, ValueError) as exc:
            raise MythchainError("Malformed committed transaction response") from exc
        if code:
            raw_log = response.get("raw_log", response.get("rawLog", "transaction failed"))
            raise MythchainError(f"Mythchain transaction committed but failed ({code}): {raw_log}")
        return response

    def query_task(self, task_id):
        response = self._run(["query", "mythprotocol", "task-lease", "--task-id", task_id])
        found = response.get("found", response.get("Found", False)) if isinstance(response, dict) else False
        lease = self._lease(response)
        if not found and not lease:
            return None
        if lease is None:
            raise MythchainError("Mythchain says task exists but returned no lease state")
        return lease

    def current_height(self):
        response = self._run(["status"])
        sync_info = response.get("sync_info", response.get("syncInfo", {})) if isinstance(response, dict) else {}
        raw_height = sync_info.get("latest_block_height", sync_info.get("latestBlockHeight"))
        try:
            return int(raw_height)
        except (TypeError, ValueError) as exc:
            raise MythchainError("Could not read latest committed block height from Mythchain status") from exc

    def _committed_tx_error(self, tx_hash):
        if not tx_hash:
            return None
        try:
            response = self._run(["query", "tx", tx_hash])
        except MythchainError as exc:
            if "not found" in str(exc).lower():
                return None
            raise
        try:
            code = int(response.get("code", 0))
        except (AttributeError, TypeError, ValueError) as exc:
            raise MythchainError("Malformed committed transaction response") from exc
        if code:
            raw_log = response.get("raw_log", response.get("rawLog", "transaction failed"))
            raise MythchainError(f"Mythchain transaction committed but failed ({code}): {raw_log}")
        return response

    def register_task(self, task_id, acceptance_hash, criteria=None, *, difficulty=None, profile=None):
        criteria_json = _canonical_criteria_json(criteria)
        task_category = reward_category_for_task(difficulty=difficulty, profile=profile) if criteria_json else ""

        def verify_registered(record):
            if record.get("acceptance_hash", record.get("acceptanceHash")) != acceptance_hash:
                return False
            stored_category = record.get("task_category", record.get("taskCategory", ""))
            return _state_criteria_json(record) == criteria_json and stored_category == task_category

        existing = self.query_task(task_id)
        if existing is not None:
            if not verify_registered(existing):
                raise MythchainError("Task ID is already registered with a different acceptance hash, criteria rubric, or reward category")
            return existing
        try:
            command = ["tx", "mythprotocol", "register-task", "--task-id", task_id,
                       "--acceptance-hash", acceptance_hash]
            if criteria_json:
                command.extend(["--criteria-json", criteria_json])
                command.extend(["--task-category", task_category])
            self._run(command, tx=True)
        except MythchainError:
            # A concurrent/retried registration may have committed despite a CLI
            # response error. Query state before deciding it failed.
            existing = self.query_task(task_id)
            if existing is None or not verify_registered(existing):
                raise
        deadline = time.monotonic() + min(self.config.timeout, 30)
        while True:
            existing = self.query_task(task_id)
            if existing is not None:
                if not verify_registered(existing):
                    raise MythchainError("Registered task acceptance hash, criteria rubric, or reward category does not match")
                return existing
            if time.monotonic() >= deadline:
                raise MythchainUnavailable("Task registration was not visible in committed chain state")
            self.sleep(1)

    def claim_task(self, task_id, acceptance_hash, criteria=None):
        """Submit a chain claim and return it only if canonical state names us owner."""
        existing = self.query_task(task_id)
        if existing is None:
            raise MythchainError("Task is not registered on Mythchain")
        if existing.get("acceptance_hash", existing.get("acceptanceHash")) != acceptance_hash:
            raise MythchainError("Task acceptance hash differs from canonical Mythchain state")
        expected_criteria = _canonical_criteria_json(criteria)
        if _state_criteria_json(existing) != expected_criteria:
            raise MythchainError("Task weighted criteria differ from canonical Mythchain state")

        current_height = self.current_height()
        status = str(existing.get("status", "")).upper()
        owner = existing.get("miner_address", existing.get("minerAddress", ""))
        attempt = existing.get("attempt_id", existing.get("attemptId", ""))
        expiry = existing.get("expires_at_height", existing.get("expiresAtHeight", 0))
        try:
            active = int(expiry) > current_height
        except (TypeError, ValueError):
            active = False
        if status == "APPROVED":
            return None
        if status == "SUBMITTED" and active:
            return None
        if status == "LEASED" and active and owner and owner != self.config.address:
            return None
        if status == "LEASED" and active and owner == self.config.address and attempt:
            return existing

        nonce = secrets.token_hex(32)
        try:
            self._run(["tx", "mythprotocol", "claim-task", "--task-id", task_id,
                       "--acceptance-hash", acceptance_hash, "--lease-blocks",
                       str(self.config.lease_blocks), "--nonce", nonce], tx=True)
        except MythchainError:
            # A competing claim may win the same block. Canonical query below
            # decides; the local transaction result is not treated as ownership.
            pass

        deadline = time.monotonic() + min(self.config.timeout, 30)
        while True:
            canonical = self.query_task(task_id)
            if canonical is not None:
                current_height = self.current_height()
                canonical_hash = canonical.get("acceptance_hash", canonical.get("acceptanceHash"))
                canonical_owner = canonical.get("miner_address", canonical.get("minerAddress", ""))
                canonical_status = str(canonical.get("status", "")).upper()
                canonical_attempt = canonical.get("attempt_id", canonical.get("attemptId", ""))
                canonical_expiry = canonical.get("expires_at_height", canonical.get("expiresAtHeight", 0))
                try:
                    canonical_active = int(canonical_expiry) > current_height
                except (TypeError, ValueError):
                    canonical_active = False
                if canonical_hash != acceptance_hash:
                    raise MythchainError("Canonical acceptance hash changed while claiming task")
                if (canonical_owner == self.config.address and canonical_attempt
                        and canonical_status == "LEASED" and canonical_active):
                    return canonical
                if (canonical_status == "APPROVED"
                        or (canonical_status == "SUBMITTED" and canonical_active)
                        or (canonical_status == "LEASED" and canonical_active
                            and canonical_owner != self.config.address)):
                    return None
            if time.monotonic() >= deadline:
                raise MythchainUnavailable("Could not confirm canonical task ownership before timeout")
            self.sleep(1)

    def release_task(self, task_id, attempt_id):
        """Release this miner's unused canonical lease and confirm committed state."""
        if not re.fullmatch(r"[0-9a-f]{64}", attempt_id or ""):
            raise MythchainError("attempt_id must be a lowercase SHA-256 hex string")
        lease = self.query_task(task_id)
        if lease is None:
            raise MythchainError("Task is not registered on Mythchain")
        owner = self._value(lease, "miner_address", "minerAddress", "")
        canonical_attempt = self._value(lease, "attempt_id", "attemptId", "")
        status = str(lease.get("status", "")).upper()
        if owner != self.config.address or canonical_attempt != attempt_id:
            raise MythchainError("Cannot release task: miner/attempt does not own the canonical lease")
        if status == "RELEASED":
            return lease
        if status != "LEASED":
            raise MythchainError(f"Cannot release task while chain status is {status or 'unknown'}")

        tx_hash = ""
        try:
            response = self._run([
                "tx", "mythprotocol", "release-task", "--task-id", task_id,
                "--attempt-id", attempt_id,
            ], tx=True)
            tx_hash = response.get("txhash", response.get("txHash", "")) if isinstance(response, dict) else ""
        except MythchainError:
            current = self.query_task(task_id)
            if (current and self._value(current, "miner_address", "minerAddress", "") == self.config.address
                    and self._value(current, "attempt_id", "attemptId", "") == attempt_id
                    and str(current.get("status", "")).upper() == "RELEASED"):
                return current
            raise

        deadline = time.monotonic() + min(self.config.timeout, 30)
        while True:
            current = self.query_task(task_id)
            if current is not None:
                current_owner = self._value(current, "miner_address", "minerAddress", "")
                current_attempt = self._value(current, "attempt_id", "attemptId", "")
                current_status = str(current.get("status", "")).upper()
                if current_attempt != attempt_id or current_owner != self.config.address:
                    raise MythchainError("Canonical lease changed while release was being committed")
                if current_status == "RELEASED":
                    return current
                if current_status != "LEASED":
                    raise MythchainError(f"Lease release was not accepted; chain status is {current_status}")
            self._check_committed_tx(tx_hash)
            if time.monotonic() >= deadline:
                raise MythchainUnavailable("Lease release was not visible in committed chain state before timeout")
            self.sleep(1)

    def submit_task_result(self, task_id, attempt_id, result_cid, proof_hash):
        """Commit an artifact CID/proof hash for this miner's active chain attempt."""
        if not re.fullmatch(r"[0-9a-f]{64}", attempt_id or ""):
            raise MythchainError("attempt_id must be a lowercase SHA-256 hex string")
        if not isinstance(result_cid, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", result_cid):
            raise MythchainError("result_cid must be sha256:<64 lowercase hex characters>")
        if not re.fullmatch(r"[0-9a-f]{64}", proof_hash or ""):
            raise MythchainError("proof_hash must be a lowercase SHA-256 hex string")

        lease = self.query_task(task_id)
        if lease is None:
            raise MythchainError("Task is not registered on Mythchain")
        owner = self._value(lease, "miner_address", "minerAddress", "")
        canonical_attempt = self._value(lease, "attempt_id", "attemptId", "")
        status = str(lease.get("status", "")).upper()
        if owner != self.config.address or canonical_attempt != attempt_id:
            raise MythchainError("Cannot submit result: miner/attempt does not own the canonical lease")
        if status == "SUBMITTED":
            if (self._value(lease, "result_cid", "resultCid") == result_cid
                    and self._value(lease, "proof_hash", "proofHash") == proof_hash):
                return lease
            raise MythchainError("A different result is already committed for this attempt")
        if status != "LEASED":
            raise MythchainError(f"Cannot submit result while chain task status is {status or 'unknown'}")
        if int(self._value(lease, "expires_at_height", "expiresAtHeight", 0)) <= self.current_height():
            raise MythchainError("Cannot submit result: canonical lease has expired")

        tx_hash = ""
        try:
            response = self._run([
                "tx", "mythprotocol", "submit-task-result", "--task-id", task_id,
                "--attempt-id", attempt_id, "--result-cid", result_cid, "--proof-hash", proof_hash,
            ], tx=True)
            tx_hash = response.get("txhash", response.get("txHash", "")) if isinstance(response, dict) else ""
        except MythchainError:
            # A retry may observe the same operation already committed.
            current = self.query_task(task_id)
            if (current and self._value(current, "attempt_id", "attemptId") == attempt_id
                    and str(current.get("status", "")).upper() == "SUBMITTED"
                    and self._value(current, "result_cid", "resultCid") == result_cid
                    and self._value(current, "proof_hash", "proofHash") == proof_hash):
                return current
            raise

        deadline = time.monotonic() + min(self.config.timeout, 30)
        while True:
            current = self.query_task(task_id)
            if current is not None:
                current_attempt = self._value(current, "attempt_id", "attemptId", "")
                current_owner = self._value(current, "miner_address", "minerAddress", "")
                current_status = str(current.get("status", "")).upper()
                if current_attempt != attempt_id or current_owner != self.config.address:
                    raise MythchainError("Canonical lease changed while result was being committed")
                if current_status == "SUBMITTED":
                    if (self._value(current, "result_cid", "resultCid") != result_cid
                            or self._value(current, "proof_hash", "proofHash") != proof_hash):
                        raise MythchainError("Committed result does not match submitted CID/proof hash")
                    return current
                if current_status != "LEASED":
                    raise MythchainError(f"Result was not accepted; chain task status is {current_status}")
            self._committed_tx_error(tx_hash)
            if time.monotonic() >= deadline:
                raise MythchainUnavailable("Result was not visible in committed chain state before timeout")
            self.sleep(1)

    def vote_task(self, task_id, attempt_id, verdict, reason="", acceptance_hash=None, result_cid=None,
                  criteria_results=None, criteria=None):
        """Commit one Cosmos-authenticated judge vote and confirm its chain state."""
        verdict = str(verdict).upper()
        if verdict not in {"PASS", "FAIL"}:
            raise MythchainError("Judge verdict must be PASS or FAIL")
        if not isinstance(reason, str) or len(reason) > 2000:
            raise MythchainError("Judge reason must be text no longer than 2000 characters")
        if not re.fullmatch(r"[0-9a-f]{64}", attempt_id or ""):
            raise MythchainError("attempt_id must be a lowercase SHA-256 hex string")

        lease = self.query_task(task_id)
        if lease is None:
            raise MythchainError("Task is not registered on Mythchain")
        if self._value(lease, "attempt_id", "attemptId") != attempt_id:
            raise MythchainError("Cannot vote: attempt_id is not the canonical task attempt")
        if acceptance_hash is not None and self._value(lease, "acceptance_hash", "acceptanceHash") != acceptance_hash:
            raise MythchainError("Cannot vote: acceptance hash differs from canonical task state")
        if result_cid is not None and self._value(lease, "result_cid", "resultCid") != result_cid:
            raise MythchainError("Cannot vote: CID differs from the canonical submitted result")
        if str(lease.get("status", "")).upper() != "SUBMITTED":
            raise MythchainError("Cannot vote before the result is committed on Mythchain")
        if int(self._value(lease, "expires_at_height", "expiresAtHeight", 0)) <= self.current_height():
            raise MythchainError("Cannot vote: submitted attempt has expired")

        def matching_vote(record):
            return (self._value(record, "judge_address", "judgeAddress") == self.config.address
                    and self._value(record, "attempt_id", "attemptId") == attempt_id)

        for record in self._votes(lease):
            if matching_vote(record):
                if (str(record.get("verdict", "")).upper() == verdict
                        and record.get("reason", "") == reason):
                    return lease
                raise MythchainError("This judge address already voted differently for this attempt")

        tx_hash = ""
        try:
            response = self._run([
                "tx", "mythprotocol", "vote-task", "--task-id", task_id,
                "--attempt-id", attempt_id, "--verdict", verdict, "--reason", reason,
            ], tx=True)
            tx_hash = response.get("txhash", response.get("txHash", "")) if isinstance(response, dict) else ""
        except MythchainError:
            current = self.query_task(task_id)
            if current is not None:
                for record in self._votes(current):
                    if (matching_vote(record) and str(record.get("verdict", "")).upper() == verdict
                            and record.get("reason", "") == reason):
                        return current
            raise

        deadline = time.monotonic() + min(self.config.timeout, 30)
        while True:
            current = self.query_task(task_id)
            if current is not None:
                if self._value(current, "attempt_id", "attemptId") != attempt_id:
                    raise MythchainError("Canonical attempt changed while judge vote was being committed")
                for record in self._votes(current):
                    if (matching_vote(record) and str(record.get("verdict", "")).upper() == verdict
                            and record.get("reason", "") == reason):
                        return current
                if str(current.get("status", "")).upper() not in {"SUBMITTED", "APPROVED", "REJECTED"}:
                    raise MythchainError("Chain task left the submitted state while voting")
            self._committed_tx_error(tx_hash)
            if time.monotonic() >= deadline:
                raise MythchainUnavailable("Judge vote was not visible in committed chain state before timeout")
            self.sleep(1)

    def submit_task_result(self, task_id, attempt_id, result_cid, proof_hash):
        """Commit the artifact/proof hashes only for this miner's active attempt."""
        if not re.fullmatch(r"[0-9a-f]{64}", attempt_id or ""):
            raise MythchainError("attempt_id must be a lowercase SHA-256 hex string")
        if not isinstance(result_cid, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", result_cid):
            raise MythchainError("result_cid must be sha256:<64 lowercase hex characters>")
        if not re.fullmatch(r"[0-9a-f]{64}", proof_hash or ""):
            raise MythchainError("proof_hash must be a lowercase SHA-256 hex string")

        lease = self.query_task(task_id)
        if lease is None:
            raise MythchainError("Task is not registered on Mythchain")
        owner = self._value(lease, "miner_address", "minerAddress", "")
        canonical_attempt = self._value(lease, "attempt_id", "attemptId", "")
        status = str(lease.get("status", "")).upper()
        if owner != self.config.address or canonical_attempt != attempt_id:
            raise MythchainError("Cannot submit result: this miner/attempt does not own the canonical lease")
        if status == "SUBMITTED":
            if (self._value(lease, "result_cid", "resultCid") == result_cid
                    and self._value(lease, "proof_hash", "proofHash") == proof_hash):
                return lease
            raise MythchainError("A different result is already committed for this attempt")
        if status != "LEASED":
            raise MythchainError(f"Cannot submit result while chain task status is {status or 'unknown'}")
        expiry = self._value(lease, "expires_at_height", "expiresAtHeight", 0)
        if int(expiry) <= self.current_height():
            raise MythchainError("Cannot submit result: canonical lease has expired")

        tx_hash = ""
        try:
            tx = self._run(["tx", "mythprotocol", "submit-task-result", "--task-id", task_id,
                            "--attempt-id", attempt_id, "--result-cid", result_cid,
                            "--proof-hash", proof_hash], tx=True)
            tx_hash = tx.get("txhash", tx.get("txHash", "")) if isinstance(tx, dict) else ""
        except MythchainError:
            # A retry may observe the state committed by the prior request.
            lease = self.query_task(task_id)
            if (lease and self._value(lease, "attempt_id", "attemptId") == attempt_id
                    and str(lease.get("status", "")).upper() == "SUBMITTED"
                    and self._value(lease, "result_cid", "resultCid") == result_cid
                    and self._value(lease, "proof_hash", "proofHash") == proof_hash):
                return lease
            raise

        deadline = time.monotonic() + min(self.config.timeout, 30)
        while True:
            current = self.query_task(task_id)
            if current is not None:
                current_attempt = self._value(current, "attempt_id", "attemptId", "")
                current_owner = self._value(current, "miner_address", "minerAddress", "")
                status = str(current.get("status", "")).upper()
                if current_attempt != attempt_id or current_owner != self.config.address:
                    raise MythchainError("Canonical lease changed while result was being committed")
                if status == "SUBMITTED":
                    if (self._value(current, "result_cid", "resultCid") != result_cid
                            or self._value(current, "proof_hash", "proofHash") != proof_hash):
                        raise MythchainError("Committed result does not match submitted CID/proof hash")
                    return current
                if status != "LEASED":
                    raise MythchainError(f"Result was not accepted; chain task status is {status}")
            self._check_committed_tx(tx_hash)
            if time.monotonic() >= deadline:
                raise MythchainUnavailable("Result transaction did not become visible in committed chain state")
            self.sleep(1)

    def vote_task(self, task_id, attempt_id, verdict, reason="", acceptance_hash=None, result_cid=None,
                  criteria_results=None, criteria=None):
        """Commit an authenticated binary or weighted judge vote and confirm chain state."""
        verdict = str(verdict).upper()
        if verdict not in {"PASS", "FAIL"}:
            raise MythchainError("Judge verdict must be PASS or FAIL")
        if not isinstance(reason, str) or len(reason) > 2000:
            raise MythchainError("Judge reason must be text no longer than 2000 characters")
        if not re.fullmatch(r"[0-9a-f]{64}", attempt_id or ""):
            raise MythchainError("attempt_id must be a lowercase SHA-256 hex string")

        lease = self.query_task(task_id)
        if lease is None:
            raise MythchainError("Task is not registered on Mythchain")
        if self._value(lease, "attempt_id", "attemptId") != attempt_id:
            raise MythchainError("Cannot vote: attempt_id is not the canonical task attempt")
        if acceptance_hash is not None and self._value(lease, "acceptance_hash", "acceptanceHash") != acceptance_hash:
            raise MythchainError("Cannot vote: acceptance hash differs from canonical task state")
        if result_cid is not None and self._value(lease, "result_cid", "resultCid") != result_cid:
            raise MythchainError("Cannot vote: result CID differs from canonical submitted artifact")
        criteria_json = _state_criteria_json(lease)
        if criteria is not None and _canonical_criteria_json(criteria) != criteria_json:
            raise MythchainError("Local judge rubric differs from canonical Mythchain task criteria")
        criteria_results_json = ""
        if criteria_json:
            criteria_results_json, score = _canonical_criteria_results_json(criteria_json, criteria_results)
            expected_verdict = "PASS" if score["status"] == "PASSED" else "FAIL"
            if verdict != expected_verdict:
                raise MythchainError("Judge verdict does not match the weighted criterion results")
        elif criteria_results is not None:
            raise MythchainError("Task has no weighted criteria; per-criterion results are not accepted")

        for vote in self._votes(lease):
            judge = self._value(vote, "judge_address", "judgeAddress", "")
            if judge == self.config.address:
                if (self._value(vote, "attempt_id", "attemptId") == attempt_id
                        and str(vote.get("verdict", "")).upper() == verdict
                        and vote.get("reason", "") == reason
                        and vote.get("criteria_results_json", vote.get("criteriaResultsJson", ""))
                        == criteria_results_json):
                    return lease
                raise MythchainError("This judge address already voted differently for this attempt")

        status = str(lease.get("status", "")).upper()
        if status != "SUBMITTED":
            raise MythchainError(f"Cannot vote while chain task status is {status or 'unknown'}")
        expiry = self._value(lease, "expires_at_height", "expiresAtHeight", 0)
        if int(expiry) <= self.current_height():
            raise MythchainError("Cannot vote: submitted attempt has expired")

        tx_hash = ""
        try:
            command = ["tx", "mythprotocol", "vote-task", "--task-id", task_id,
                       "--attempt-id", attempt_id, "--verdict", verdict, "--reason", reason]
            if criteria_results_json:
                command.extend(["--criteria-results-json", criteria_results_json])
            tx = self._run(command, tx=True)
            tx_hash = tx.get("txhash", tx.get("txHash", "")) if isinstance(tx, dict) else ""
        except MythchainError:
            # Treat retries idempotently only if this exact signed judge vote is on chain.
            lease = self.query_task(task_id)
            if lease is not None:
                for vote in self._votes(lease):
                    if (self._value(vote, "judge_address", "judgeAddress") == self.config.address
                            and self._value(vote, "attempt_id", "attemptId") == attempt_id
                            and str(vote.get("verdict", "")).upper() == verdict
                            and vote.get("reason", "") == reason
                            and vote.get("criteria_results_json", vote.get("criteriaResultsJson", ""))
                            == criteria_results_json):
                        return lease
            raise

        deadline = time.monotonic() + min(self.config.timeout, 30)
        while True:
            current = self.query_task(task_id)
            if current is not None:
                current_attempt = self._value(current, "attempt_id", "attemptId", "")
                if current_attempt != attempt_id:
                    raise MythchainError("Canonical attempt changed while judge vote was being committed")
                for vote in self._votes(current):
                    if (self._value(vote, "judge_address", "judgeAddress") == self.config.address
                            and self._value(vote, "attempt_id", "attemptId") == attempt_id
                            and str(vote.get("verdict", "")).upper() == verdict
                            and vote.get("reason", "") == reason
                            and vote.get("criteria_results_json", vote.get("criteriaResultsJson", ""))
                            == criteria_results_json):
                        return current
            self._check_committed_tx(tx_hash)
            if time.monotonic() >= deadline:
                raise MythchainUnavailable("Judge vote did not become visible in committed chain state")
            self.sleep(1)
