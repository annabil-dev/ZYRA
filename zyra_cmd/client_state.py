"""Durable, machine-local CLI preferences and submitted task history."""

import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


def default_data_dir():
    return Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "ZYRA AI"


class ClientState:
    def __init__(self, data_dir=None):
        data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "client.db"
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS client_tasks (
                    task_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_cid TEXT,
                    download_status TEXT NOT NULL DEFAULT 'pending',
                    result_path TEXT,
                    zip_path TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get_setting(self, name, default=None):
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE name = ?", (name,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, name, value):
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (name, json.dumps(value)))

    def get_output_dir(self):
        return Path(self.get_setting("output_dir", str(Path.home() / "ZYRA Results")))

    def set_output_dir(self, value):
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not value.strip():
            raise ValueError("Folder hasil tidak boleh kosong.")
        path = Path(os.path.expandvars(value)).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        # Check write access before remembering the user's choice.
        with tempfile.TemporaryFile(dir=path):
            pass
        self.set_setting("output_dir", str(path))
        return path

    def add_task(self, payload):
        now = time.time()
        # Snapshot an absolute destination; future /output changes cannot move this task.
        output_dir = str(self.get_output_dir().resolve())
        with self._connect() as db:
            db.execute("""
                INSERT INTO client_tasks
                (task_id, payload, output_dir, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (payload["task_id"], json.dumps(payload), output_dir,
                  payload.get("status", "pending"), now, now))
        return self.get_task(payload["task_id"])

    def get_task(self, task_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM client_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self):
        with self._connect() as db:
            rows = db.execute("SELECT * FROM client_tasks ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def update_from_network(self, payload):
        """Persist only tasks submitted on this machine, never peer-supplied paths."""
        with self._connect() as db:
            row = db.execute("SELECT * FROM client_tasks WHERE task_id = ?",
                             (payload.get("task_id"),)).fetchone()
            if not row or row["download_status"] == "downloaded":
                return
            status = payload.get("status", row["status"])
            if status not in {"pending", "mining", "validating", "completed", "rejected", "failed"}:
                status = row["status"]
            # An old mempool snapshot must not roll back an observed completion.
            if row["status"] == "completed":
                status = "completed"
            cid = payload.get("result_cid") or row["result_cid"]
            if row["status"] == "completed" and row["result_cid"]:
                cid = row["result_cid"]
            if cid is not None and not isinstance(cid, str):
                cid = row["result_cid"]
            if status != row["status"] or cid != row["result_cid"]:
                db.execute("""UPDATE client_tasks SET status = ?, result_cid = ?, updated_at = ?
                              WHERE task_id = ?""", (status, cid, time.time(), row["task_id"]))

    def set_download(self, task_id, status, *, result_path=None, zip_path=None, error=None):
        with self._connect() as db:
            db.execute("""UPDATE client_tasks
                          SET download_status = ?, result_path = COALESCE(?, result_path),
                              zip_path = COALESCE(?, zip_path), error = ?, updated_at = ?
                          WHERE task_id = ?""",
                       (status, str(result_path) if result_path else None,
                        str(zip_path) if zip_path else None, error, time.time(), task_id))
