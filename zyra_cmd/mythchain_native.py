"""Native Cosmos SDK signing and gRPC transport for Mythchain.

The node binary is not invoked here. Transactions are built and signed locally
with CosmPy, then sent to the Cosmos gRPC Tx service. Custom Mythchain messages
are represented with protobuf descriptors that match the chain's public proto.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from urllib.parse import quote, urlparse

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
import grpc
import requests

from cosmpy.aerial.client import LedgerClient, NetworkConfig
from cosmpy.aerial.tx import SigningCfg, Transaction, TxFee
from cosmpy.aerial.wallet import LocalWallet
from cosmpy.crypto.address import Address
from cosmpy.crypto.keypairs import PrivateKey

from zyra_cmd.mythchain_adapter import MythchainError, MythchainUnavailable


_PACKAGE = "mythprotocol.mythprotocol.v1"
_FILE = "zyra_mythprotocol_native.proto"
MYTHCHAIN_DISPLAY_DENOMS = {"umtc": "MTC", "uzyra": "ZYRA"}
MICRO_DENOM_SCALE = 1_000_000


class NativeMythchainQueryClient:
    """Read public Cosmos bank state without loading a signing key."""

    def __init__(self, config, ledger_client_factory=None):
        self.config = config
        try:
            network = NetworkConfig(
                chain_id=config.chain_id,
                fee_minimum_gas_price=0,
                fee_denomination="umtc",
                staking_denomination="umtc",
                url=config.grpc_endpoint,
            )
            factory = ledger_client_factory or LedgerClient
            self.ledger = factory(network, query_timeout_secs=config.timeout)
            actual_chain_id = self.ledger.query_chain_id()
        except Exception as exc:
            raise MythchainUnavailable(f"Could not query Mythchain endpoint: {exc}") from exc
        if actual_chain_id != config.chain_id:
            raise MythchainError(
                f"Configured chain ID {config.chain_id!r} does not match endpoint chain ID "
                f"{actual_chain_id!r}"
            )

    def query_bank_balances(self, address=None):
        account = address or self.config.address
        try:
            coins = self.ledger.query_bank_all_balances(Address(account))
            return {coin.denom: int(coin.amount) for coin in coins}
        except Exception as exc:
            raise MythchainUnavailable(f"Could not query bank balances for {account}: {exc}") from exc

    def query_staking_summary(self, address=None):
        account = address or self.config.address
        try:
            summary = self.ledger.query_staking_summary(Address(account))
            return {
                "delegations": [{
                    "validator": str(position.validator),
                    "amount_umtc": int(position.amount),
                    "rewards_umtc": int(position.reward),
                } for position in summary.current_positions],
                "unbonding": [{
                    "validator": str(position.validator),
                    "amount_umtc": int(position.amount),
                } for position in summary.unbonding_positions],
            }
        except Exception as exc:
            raise MythchainUnavailable(f"Could not query staking positions for {account}: {exc}") from exc


def _field(message, name, number, field_type, *, repeated=False, type_name=""):
    item = message.field.add()
    item.name = name
    item.number = number
    item.label = (descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED if repeated
                  else descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL)
    item.type = field_type
    if type_name:
        item.type_name = type_name


def _native_messages():
    """Return generated-compatible message classes for the exact wire schema."""
    pool = descriptor_pool.Default()
    try:
        pool.FindFileByName(_FILE)
    except KeyError:
        file_proto = descriptor_pb2.FileDescriptorProto()
        file_proto.name = _FILE
        file_proto.package = _PACKAGE
        file_proto.syntax = "proto3"

        string = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
        int64 = descriptor_pb2.FieldDescriptorProto.TYPE_INT64
        uint64 = descriptor_pb2.FieldDescriptorProto.TYPE_UINT64
        boolean = descriptor_pb2.FieldDescriptorProto.TYPE_BOOL
        message_type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
        prefix = f".{_PACKAGE}."

        vote = file_proto.message_type.add()
        vote.name = "TaskVote"
        for name, number, kind in (
            ("judge_address", 1, string), ("attempt_id", 2, string),
            ("verdict", 3, string), ("reason", 4, string),
            ("height", 5, int64), ("criteria_results_json", 6, string),
        ):
            _field(vote, name, number, kind)

        lease = file_proto.message_type.add()
        lease.name = "TaskLease"
        for name, number, kind in (
            ("task_id", 1, string), ("acceptance_hash", 2, string),
            ("miner_address", 3, string), ("attempt_id", 4, string),
            ("start_height", 5, int64), ("expires_at_height", 6, int64),
            ("status", 7, string), ("result_cid", 8, string),
            ("proof_hash", 9, string), ("client_address", 10, string),
        ):
            _field(lease, name, number, kind)
        _field(lease, "votes", 11, message_type, repeated=True, type_name=prefix + "TaskVote")
        for name, number, kind in (
            ("criteria_json", 12, string), ("canonical_criteria_results_json", 13, string),
            ("criteria_score_numerator", 14, uint64),
            ("criteria_score_denominator", 15, uint64), ("task_category", 16, string),
            ("reward_settled", 17, boolean), ("reward_amount_uzyra", 18, uint64),
        ):
            _field(lease, name, number, kind)
        _field(lease, "judge_reward_addresses", 19, string, repeated=True)

        for message_name, fields in (
            ("MsgRegisterTask", (("creator", 1, string), ("task_id", 2, string),
                                 ("acceptance_hash", 3, string), ("criteria_json", 4, string),
                                 ("task_category", 5, string))),
            ("MsgClaimTask", (("creator", 1, string), ("task_id", 2, string),
                              ("acceptance_hash", 3, string), ("lease_blocks", 4, uint64),
                              ("nonce", 5, string))),
            ("MsgReleaseTask", (("creator", 1, string), ("task_id", 2, string),
                                ("attempt_id", 3, string))),
            ("MsgSubmitTaskResult", (("creator", 1, string), ("task_id", 2, string),
                                      ("attempt_id", 3, string), ("result_cid", 4, string),
                                      ("proof_hash", 5, string))),
            ("MsgVoteTask", (("creator", 1, string), ("task_id", 2, string),
                              ("attempt_id", 3, string), ("verdict", 4, string),
                              ("reason", 5, string), ("criteria_results_json", 6, string))),
            ("QueryTaskLeaseRequest", (("task_id", 1, string),)),
        ):
            message = file_proto.message_type.add()
            message.name = message_name
            for name, number, kind in fields:
                _field(message, name, number, kind)

        response = file_proto.message_type.add()
        response.name = "QueryTaskLeaseResponse"
        _field(response, "lease", 1, message_type, type_name=prefix + "TaskLease")
        _field(response, "found", 2, boolean)
        pool.AddSerializedFile(file_proto.SerializeToString())

    def cls(name):
        return message_factory.GetMessageClass(pool.FindMessageTypeByName(f"{_PACKAGE}.{name}"))

    return {name: cls(name) for name in (
        "TaskVote", "TaskLease", "MsgRegisterTask", "MsgClaimTask", "MsgReleaseTask",
        "MsgSubmitTaskResult", "MsgVoteTask", "QueryTaskLeaseRequest", "QueryTaskLeaseResponse",
    )}


class NativeMythchainClient:
    """Cosmos direct-sign client for queries and Mythchain module transactions."""

    def __init__(self, config):
        self.config = config
        messages = _native_messages()
        self._messages = messages
        self._query_request = messages["QueryTaskLeaseRequest"]
        self._query_response = messages["QueryTaskLeaseResponse"]

        secret_path = config.mnemonic_file or config.private_key_file
        if not secret_path:
            raise MythchainError(
                "Native signing requires MYTHCHAIN_<ROLE>_MNEMONIC_FILE or "
                "MYTHCHAIN_<ROLE>_PRIVATE_KEY_FILE"
            )
        try:
            secret = Path(secret_path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise MythchainError(f"Could not read native signing key file: {secret_path}") from exc
        if not secret:
            raise MythchainError("Native signing key file is empty")

        try:
            if config.mnemonic_file:
                self.wallet = LocalWallet.from_mnemonic(secret, prefix="myth")
            else:
                private_hex = secret.removeprefix("0x")
                self.wallet = LocalWallet(PrivateKey(bytes.fromhex(private_hex)), prefix="myth")
        except Exception as exc:
            raise MythchainError("Could not derive Cosmos wallet from native signing key file") from exc

        derived_address = str(self.wallet.address())
        if derived_address != config.address:
            raise MythchainError(
                f"Configured Cosmos address {config.address} does not match key-derived address "
                f"{derived_address}"
            )

        try:
            network = NetworkConfig(
                chain_id=config.chain_id,
                fee_minimum_gas_price=0,
                fee_denomination="umtc",
                staking_denomination="umtc",
                url=config.grpc_endpoint,
            )
            self.ledger = LedgerClient(network, query_timeout_secs=config.timeout)
        except Exception as exc:
            raise MythchainUnavailable(f"Could not initialize Cosmos gRPC client: {exc}") from exc

        endpoint_transport = config.grpc_endpoint.split("+", 1)[1]
        parsed = urlparse(endpoint_transport)
        self._rest_endpoint = ""
        self._query_channel = None
        self._query_rpc = None
        if config.grpc_endpoint.startswith("grpc+"):
            try:
                if parsed.scheme == "https":
                    channel = grpc.secure_channel(parsed.netloc, grpc.ssl_channel_credentials())
                else:
                    channel = grpc.insecure_channel(parsed.netloc)
                self._query_channel = channel
                self._query_rpc = channel.unary_unary(
                    "/mythprotocol.mythprotocol.v1.Query/TaskLease",
                    request_serializer=lambda request: request.SerializeToString(),
                    response_deserializer=self._query_response.FromString,
                )
            except Exception as exc:
                raise MythchainUnavailable(f"Could not initialize Mythchain query gRPC: {exc}") from exc
        else:
            self._rest_endpoint = endpoint_transport.rstrip("/")

        try:
            actual_chain_id = self.ledger.query_chain_id()
        except Exception as exc:
            raise MythchainUnavailable(f"Could not query chain ID over Cosmos endpoint: {exc}") from exc
        if actual_chain_id != config.chain_id:
            raise MythchainError(
                f"Configured chain ID {config.chain_id!r} does not match endpoint chain ID "
                f"{actual_chain_id!r}"
            )

    def _query_task(self, task_id):
        try:
            if self._query_rpc is not None:
                response = self._query_rpc(
                    self._query_request(task_id=task_id), timeout=self.config.timeout
                )
                if not response.found:
                    return None
                lease = response.lease
                return {
                    "task_id": lease.task_id,
                    "acceptance_hash": lease.acceptance_hash,
                    "miner_address": lease.miner_address,
                    "attempt_id": lease.attempt_id,
                    "start_height": str(lease.start_height),
                    "expires_at_height": str(lease.expires_at_height),
                    "status": lease.status,
                    "result_cid": lease.result_cid,
                    "proof_hash": lease.proof_hash,
                    "client_address": lease.client_address,
                    "votes": [{
                        "judge_address": vote.judge_address,
                        "attempt_id": vote.attempt_id,
                        "verdict": vote.verdict,
                        "reason": vote.reason,
                        "height": str(vote.height),
                        "criteria_results_json": vote.criteria_results_json,
                    } for vote in lease.votes],
                    "criteria_json": lease.criteria_json,
                    "canonical_criteria_results_json": lease.canonical_criteria_results_json,
                    "criteria_score_numerator": str(lease.criteria_score_numerator),
                    "criteria_score_denominator": str(lease.criteria_score_denominator),
                    "task_category": lease.task_category,
                    "reward_settled": lease.reward_settled,
                    "reward_amount_uzyra": str(lease.reward_amount_uzyra),
                    "judge_reward_addresses": list(lease.judge_reward_addresses),
                }

            response = requests.get(
                f"{self._rest_endpoint}/mythprotocol/mythprotocol/v1/tasks/"
                f"{quote(task_id, safe='')}/lease",
                timeout=self.config.timeout,
            )
            if response.status_code == 404:
                raise MythchainUnavailable(
                    "Mythchain REST task-query route returned 404; verify the REST endpoint/API is enabled"
                )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("found", payload.get("lease") is not None):
                return None
            lease = payload.get("lease")
            if not isinstance(lease, dict):
                raise MythchainError("Mythchain REST returned malformed task lease")
            return lease
        except grpc.RpcError as exc:
            raise self._rpc_error(exc) from exc
        except requests.RequestException as exc:
            raise MythchainUnavailable(f"Mythchain REST query failed: {exc}") from exc

    @staticmethod
    def _rpc_error(exc):
        code = exc.code() if hasattr(exc, "code") else None
        detail = exc.details() if hasattr(exc, "details") else str(exc)
        if code in {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED}:
            return MythchainUnavailable(f"Mythchain gRPC unavailable: {detail}")
        return MythchainError(f"Mythchain gRPC failed: {detail}")

    @staticmethod
    def _flag(args, name, default=""):
        try:
            return args[args.index(name) + 1]
        except (ValueError, IndexError):
            return default

    def _make_message(self, args):
        module, action = args[1], args[2]
        if module != "mythprotocol":
            raise MythchainError(f"Unsupported native transaction module: {module}")
        creator = self.config.address
        value = lambda name, default="": self._flag(args, name, default)
        if action == "register-task":
            return self._messages["MsgRegisterTask"](
                creator=creator, task_id=value("--task-id"),
                acceptance_hash=value("--acceptance-hash"),
                criteria_json=value("--criteria-json"), task_category=value("--task-category"),
            )
        if action == "claim-task":
            return self._messages["MsgClaimTask"](
                creator=creator, task_id=value("--task-id"),
                acceptance_hash=value("--acceptance-hash"),
                lease_blocks=int(value("--lease-blocks", "0")), nonce=value("--nonce"),
            )
        if action == "release-task":
            return self._messages["MsgReleaseTask"](
                creator=creator, task_id=value("--task-id"), attempt_id=value("--attempt-id"),
            )
        if action == "submit-task-result":
            return self._messages["MsgSubmitTaskResult"](
                creator=creator, task_id=value("--task-id"), attempt_id=value("--attempt-id"),
                result_cid=value("--result-cid"), proof_hash=value("--proof-hash"),
            )
        if action == "vote-task":
            return self._messages["MsgVoteTask"](
                creator=creator, task_id=value("--task-id"), attempt_id=value("--attempt-id"),
                verdict=value("--verdict"), reason=value("--reason"),
                criteria_results_json=value("--criteria-results-json"),
            )
        raise MythchainError(f"Unsupported native Mythchain transaction: {action}")

    def _broadcast(self, message):
        from cosmpy.aerial.tx import SigningCfg, Transaction, TxFee
        from cosmpy.aerial.exceptions import BroadcastError

        account = self.ledger.query_account(self.wallet.address())
        seq = account.sequence
        for _ in range(5):
            try:
                transaction = Transaction()
                transaction.add_message(message)
                transaction.seal(
                    SigningCfg.direct(self.wallet.public_key(), seq),
                    fee=TxFee(amount=self.config.fees or None, gas_limit=self.config.gas_limit),
                )
                transaction.sign(
                    self.wallet.signer(), self.config.chain_id, account.number, deterministic=True
                )
                transaction.complete()
                submitted = self.ledger.broadcast_tx(transaction)
                completed = submitted.wait_to_complete(
                    timeout=timedelta(seconds=self.config.timeout),
                    poll_period=timedelta(seconds=1),
                )
                response = completed.response
                return {"txhash": response.hash, "code": response.code, "raw_log": response.raw_log}
            except BroadcastError as exc:
                if 'incorrect account sequence' in str(exc).lower():
                    print(f"Retrying sequence {seq} due to {exc}")
                    seq += 1
                    import time; time.sleep(1)
                    continue
                raise MythchainError(f"Native Cosmos transaction failed: {exc}") from exc
            except grpc.RpcError as exc:
                raise self._rpc_error(exc) from exc
            except Exception as exc:
                detail = str(exc)
                if any(marker in detail.lower() for marker in (
                    "connection refused", "unavailable", "deadline exceeded", "timed out",
                )):
                    raise MythchainUnavailable(f"Native Cosmos transaction failed: {detail}") from exc
                raise MythchainError(f"Native Cosmos transaction failed: {detail}") from exc
        raise MythchainError("Failed after 5 sequence retries")

    def _complete_ledger_transaction(self, label, submit):
        from cosmpy.aerial.tx import TxFee

        try:
            submitted = submit(TxFee(
                amount=self.config.fees or None,
                gas_limit=self.config.gas_limit,
            ))
            completed = submitted.wait_to_complete(
                timeout=timedelta(seconds=self.config.timeout),
                poll_period=timedelta(seconds=1),
            )
            response = completed.response
            code = int(getattr(response, "code", 0) or 0)
            raw_log = getattr(response, "raw_log", "") or ""
            if code:
                raise MythchainError(f"Mythchain {label} failed ({code}): {raw_log}")
            return {"txhash": getattr(response, "hash", ""), "code": code, "raw_log": raw_log}
        except MythchainError:
            raise
        except grpc.RpcError as exc:
            raise self._rpc_error(exc) from exc
        except Exception as exc:
            detail = str(exc)
            if any(marker in detail.lower() for marker in (
                "connection refused", "unavailable", "deadline exceeded", "timed out",
            )):
                raise MythchainUnavailable(f"Mythchain {label} failed: {detail}") from exc
            raise MythchainError(f"Mythchain {label} failed: {detail}") from exc

    def send_bank_tokens(self, destination, amount, denom):
        return self._complete_ledger_transaction(
            "bank send",
            lambda fee: self.ledger.send_tokens(
                Address(destination), int(amount), denom, self.wallet, fee=fee,
            ),
        )

    def delegate_mtc(self, validator, amount):
        return self._complete_ledger_transaction(
            "MTC delegation",
            lambda fee: self.ledger.delegate_tokens(
                Address(validator), int(amount), self.wallet, fee=fee,
            ),
        )

    def undelegate_mtc(self, validator, amount):
        return self._complete_ledger_transaction(
            "MTC undelegation",
            lambda fee: self.ledger.undelegate_tokens(
                Address(validator), int(amount), self.wallet, fee=fee,
            ),
        )

    def run(self, args, *, tx=False):
        """Execute the adapter's internal query/tx operation without a daemon binary."""
        if not args:
            raise MythchainError("Empty native Mythchain operation")
        if args[0] == "status":
            try:
                return {"sync_info": {"latest_block_height": str(self.ledger.query_height())}}
            except Exception as exc:
                raise MythchainUnavailable(f"Could not query Mythchain block height: {exc}") from exc
        if args[0] == "query" and len(args) >= 3 and args[1] == "mythprotocol":
            if args[2] == "task-lease":
                lease = self._query_task(self._flag(args, "--task-id"))
                return {"found": lease is not None, "lease": lease}
        if args[0] == "query" and len(args) >= 3 and args[1] == "tx":
            try:
                result = self.ledger.query_tx(args[2])
                return {"txhash": result.hash, "code": result.code, "raw_log": result.raw_log}
            except Exception as exc:
                if "not found" in str(exc).lower():
                    raise MythchainError("transaction not found") from exc
                raise MythchainUnavailable(f"Could not query Mythchain transaction: {exc}") from exc
        if args[0] == "tx" and tx:
            return self._broadcast(self._make_message(args))
        raise MythchainError(f"Unsupported native Mythchain operation: {' '.join(args[:3])}")
