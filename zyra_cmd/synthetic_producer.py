"""Headless synthetic-task producer for a validator host or dedicated L1 client."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import json
import os
import random
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai.blockchain.wallet import ZyraWallet
from zyra_cmd.client_state import ClientState
from zyra_cmd.synthetic_tasks import MAX_CATALOG_TASKS, randomized_task_specs
from zyra_cmd.task_dispatch import dispatch_client_task

DEFAULT_MAX_PER_DAY = 50
DEFAULT_MIN_INTERVAL = 5 * 60
DEFAULT_MAX_INTERVAL = 30 * 60
DEFAULT_RETRY_SECONDS = 30
DEFAULT_TRACKER = "https://zyra-ai.tail3b049d.ts.net"


def _utc_day(timestamp: float | None = None) -> str:
    return datetime.fromtimestamp(timestamp or time.time(), timezone.utc).date().isoformat()


class ProducerStore:
    """Durable daily quota and outbox so a restart does not lose queued task specs."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS daily_submissions (
                    utc_day TEXT PRIMARY KEY,
                    submitted INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS synthetic_outbox (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL UNIQUE,
                    spec_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS producer_settings (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

    def _connect(self):
        @contextmanager
        def connection():
            db = sqlite3.connect(self.path, timeout=20)
            db.row_factory = sqlite3.Row
            try:
                with db:
                    yield db
            finally:
                db.close()

        return connection()

    def submitted_today(self, utc_day: str) -> int:
        with self._connect() as db:
            row = db.execute("SELECT submitted FROM daily_submissions WHERE utc_day=?", (utc_day,)).fetchone()
        return int(row["submitted"]) if row else 0

    def next_due_at(self) -> float | None:
        with self._connect() as db:
            row = db.execute("SELECT value FROM producer_settings WHERE name='next_due_at'").fetchone()
        return float(row["value"]) if row else None

    def enqueue_batch(self, specs) -> int:
        now = time.time()
        rows = [
            (str(uuid.uuid4()), json.dumps(spec, sort_keys=True, separators=(",", ":")), now + index * 0.000001)
            for index, spec in enumerate(specs)
        ]
        with self._connect() as db:
            db.executemany(
                "INSERT OR IGNORE INTO synthetic_outbox(task_id,spec_json,created_at) VALUES(?,?,?)", rows
            )
        return len(rows)

    def next_queued(self):
        with self._connect() as db:
            row = db.execute(
                "SELECT task_id,spec_json FROM synthetic_outbox ORDER BY sequence LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return {"task_id": row["task_id"], "spec": json.loads(row["spec_json"])}

    def queued_count(self) -> int:
        with self._connect() as db:
            row = db.execute("SELECT COUNT(*) AS count FROM synthetic_outbox").fetchone()
        return int(row["count"])

    def mark_submitted(self, task_id: str, utc_day: str, next_due_at: float) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM synthetic_outbox WHERE task_id=?", (task_id,))
            db.execute("""
                INSERT INTO daily_submissions(utc_day,submitted) VALUES(?,1)
                ON CONFLICT(utc_day) DO UPDATE SET submitted=submitted+1
            """, (utc_day,))
            db.execute("INSERT OR REPLACE INTO producer_settings(name,value) VALUES('next_due_at',?)",
                       (str(float(next_due_at)),))

    def restore_pending_tasks(self, client_state, p2p_node) -> int:
        restored = 0
        for row in client_state.list_tasks():
            try:
                payload = json.loads(row["payload"])
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            if (payload.get("origin") == "synthetic"
                    and row.get("status") in {"pending", "mining", "validating"}):
                p2p_node.add_task(payload)
                restored += 1
        return restored


class SyntheticTaskProducer:
    """Submit one reviewed task at random intervals, with a persistent daily cap."""

    def __init__(self, *, client_state, p2p_node, wallet, store: ProducerStore,
                 max_per_day=DEFAULT_MAX_PER_DAY, min_interval=DEFAULT_MIN_INTERVAL,
                 max_interval=DEFAULT_MAX_INTERVAL, retry_seconds=DEFAULT_RETRY_SECONDS,
                 seed=None, on_event=print):
        if not 1 <= max_per_day <= DEFAULT_MAX_PER_DAY:
            raise ValueError(f"max_per_day must be between 1 and {DEFAULT_MAX_PER_DAY}")
        if not 300 <= min_interval <= max_interval <= 1800:
            raise ValueError("intervals must satisfy 300 <= min <= max <= 1800 seconds")
        if retry_seconds < 5 or retry_seconds > 300:
            raise ValueError("retry_seconds must be between 5 and 300")
        self.client_state = client_state
        self.p2p_node = p2p_node
        self.wallet = wallet
        self.store = store
        self.max_per_day = max_per_day
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.retry_seconds = retry_seconds
        self.rng = random.Random(seed)
        self.on_event = on_event

    def _enqueue_catalog_batch(self):
        seed = self.rng.getrandbits(64)
        self.store.enqueue_batch(randomized_task_specs(seed=seed, count=MAX_CATALOG_TASKS))
        self.on_event(f"Queued a randomized batch of {MAX_CATALOG_TASKS} reviewed task templates (seed={seed}).")

    def submit_one(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        utc_day = _utc_day(now)
        submitted = self.store.submitted_today(utc_day)
        if submitted >= self.max_per_day:
            return False

        queued = self.store.next_queued()
        if queued is None:
            self._enqueue_catalog_batch()
            queued = self.store.next_queued()
        if queued is None:
            return False

        spec = queued["spec"]
        task, _saved = dispatch_client_task(
            spec["prompt"],
            spec["acceptance"],
            self.wallet,
            self.client_state,
            self.p2p_node,
            task_id=queued["task_id"],
            metadata={
                "origin": "synthetic",
                "difficulty": spec["difficulty"],
                "profile": spec["runtime_profile"],
                "synthetic_template_id": spec["template_id"],
                "synthetic_catalog_version": spec["catalog_version"],
                "synthetic_seed": spec["seed"],
            },
        )
        submitted_day = _utc_day()
        next_due_at = time.time() + self.rng.uniform(self.min_interval, self.max_interval)
        self.store.mark_submitted(task["task_id"], submitted_day, next_due_at)
        self.on_event(
            f"Submitted synthetic task {task['task_id']} ({spec['template_id']}, "
            f"{spec['reward_category']}); daily quota "
            f"{self.store.submitted_today(submitted_day)}/{self.max_per_day}."
        )
        return True

    def run_forever(self, stop_event: threading.Event | None = None):
        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            now = time.time()
            utc_day = _utc_day(now)
            submitted = self.store.submitted_today(utc_day)
            if submitted >= self.max_per_day:
                tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
                next_day = datetime.combine(tomorrow, datetime.min.time(), tzinfo=timezone.utc).timestamp()
                wait_seconds = min(60, max(1, next_day - now))
                self.on_event(f"Daily task cap reached ({submitted}/{self.max_per_day}); waiting for UTC reset.")
                stop_event.wait(wait_seconds)
                continue

            due = self.store.next_due_at()
            if due is not None and now < due:
                stop_event.wait(min(30, max(1, due - now)))
                continue

            try:
                self.submit_one(now)
            except Exception as exc:
                self.on_event(f"Task submit failed; keeping the queued task and retrying: {exc}")
                stop_event.wait(self.retry_seconds)


def _positive_int_env(name, default, *, maximum):
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _acquire_producer_lock(data_dir: Path):
    import fcntl

    lock = (data_dir / "synthetic-producer.lock").open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise RuntimeError(f"another synthetic producer is already running for {data_dir}") from exc
    return lock


def main(argv=None):
    parser = argparse.ArgumentParser(description="Autonomous, bounded Mythchain synthetic task producer")
    args = parser.parse_args(argv)
    if os.name == "nt":
        parser.error("zyra-syntheticd is a Linux service; run it on the validator host or Linux server")
    if os.environ.get("ZYRA_MYTHCHAIN_MODE", "off").lower() != "required":
        parser.error("set ZYRA_MYTHCHAIN_MODE=required so tasks are registered on the canonical chain")

    max_per_day = _positive_int_env("ZYRA_SYNTHETIC_MAX_PER_DAY", DEFAULT_MAX_PER_DAY, maximum=DEFAULT_MAX_PER_DAY)
    min_interval = _positive_int_env("ZYRA_SYNTHETIC_MIN_INTERVAL_SECONDS", DEFAULT_MIN_INTERVAL, maximum=1800)
    max_interval = _positive_int_env("ZYRA_SYNTHETIC_MAX_INTERVAL_SECONDS", DEFAULT_MAX_INTERVAL, maximum=1800)
    if min_interval < 300 or max_interval < min_interval:
        parser.error("synthetic intervals must satisfy 300 <= min <= max <= 1800 seconds")

    data_dir = Path(os.environ.get("ZYRA_DATA_DIR", Path.home() / ".local/share/zyra-synthetic"))
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        producer_lock = _acquire_producer_lock(data_dir)
    except RuntimeError as exc:
        parser.error(str(exc))
    # Keep this handle alive for the lifetime of the producer to enforce one instance.
    _ = producer_lock
    state = ClientState(data_dir)
    wallet = ZyraWallet(data_dir)
    store = ProducerStore(data_dir / "synthetic-producer.sqlite3")

    from p2p.network import P2PNode

    tracker = os.environ.get("TRACKER_URL", DEFAULT_TRACKER)
    port = int(os.environ.get("ZYRA_P2P_PORT", str(random.SystemRandom().randint(5001, 5999))))
    p2p_node = P2PNode(port=port, tracker_url=tracker,
                       seed_peer=os.environ.get("ZYRA_SEED_PEER"))
    p2p_node.on_task_updated = state.update_from_network
    if os.environ.get("ZYRA_MYTHCHAIN_MODE", "off").lower() == "required":
        from zyra_cmd.zyra_cli import make_chain_admit_filter
        admit_filter = make_chain_admit_filter()
        if admit_filter is not None:
            p2p_node.task_admit_filter = admit_filter

    loop_ready = threading.Event()

    def run_p2p():
        async def serve():
            p2p_node.loop = asyncio.get_running_loop()
            loop_ready.set()
            await p2p_node.start()
        asyncio.run(serve())

    threading.Thread(target=run_p2p, name="zyra-synthetic-p2p", daemon=True).start()
    if not loop_ready.wait(timeout=10):
        parser.error("P2P network loop did not start")
    restored = store.restore_pending_tasks(state, p2p_node)

    producer = SyntheticTaskProducer(
        client_state=state,
        p2p_node=p2p_node,
        wallet=wallet,
        store=store,
        max_per_day=max_per_day,
        min_interval=min_interval,
        max_interval=max_interval,
    )
    print(
        f"ZYRA synthetic producer online: chain={os.environ.get('MYTHCHAIN_CHAIN_ID')} "
        f"daily_cap={max_per_day} interval={min_interval}-{max_interval}s "
        f"restored_pending={restored}", flush=True,
    )
    producer.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
