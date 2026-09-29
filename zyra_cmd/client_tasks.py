"""Resume client task tracking and result downloads after a CLI restart."""

import asyncio
import json
import logging
import os
import shutil
import stat
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath


def extract_workspace(archive_path, destination):
    """Validate archive paths before extracting into a fresh staging directory."""
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if (path.is_absolute() or ".." in path.parts or ":" in member.filename
                    or stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError(f"Unsafe workspace path: {member.filename}")
        archive.extractall(destination)


class ClientTaskMonitor:
    def __init__(self, state, node, notify=print):
        self.state = state
        self.node = node
        self.notify = notify
        self._stop = threading.Event()
        self._thread = None
        self._retry_after = {}
        self._download_future = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="zyra-client-tasks", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._download_future is not None:
            self._download_future.cancel()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def show_tasks(self, startup=False):
        tasks = self.state.list_tasks()
        if not tasks:
            if not startup:
                self.notify("[Client] Belum ada task tersimpan. Gunakan /submit <task>.")
            return
        if startup:
            saved = [t for t in tasks if t["download_status"] == "downloaded"]
            pending = len(tasks) - len(saved)
            self.notify(f"\n[Client] Riwayat: {len(saved)} hasil tersimpan, {pending} task menunggu sinkronisasi/unduhan.")
            tasks = saved[:5]
        for task in tasks:
            tid = task["task_id"]
            try:
                stored_payload = json.loads(task["payload"])
            except (TypeError, json.JSONDecodeError):
                stored_payload = {}
            acceptance_report = stored_payload.get("acceptance_score_report", {})
            if task["download_status"] == "downloaded":
                self.notify(f"[Selesai] {tid}\n  Workspace: {task['result_path']}\n  ZIP: {task['zip_path']}")
            else:
                self.notify(f"[Client] {tid}: {task['status']} / unduhan {task['download_status']}\n"
                            f"  Folder tujuan: {task['output_dir']}")
                if task["error"]:
                    self.notify(f"  Kendala terakhir: {task['error']}")
            if isinstance(acceptance_report, dict) and acceptance_report.get("client_report_markdown"):
                self.notify(f"\n[Acceptance review] {tid}\n{acceptance_report['client_report_markdown']}")
        if startup:
            self.notify("[Client] Pemantauan dilanjutkan saat terhubung ke peer. Ketik /tasks untuk semua task.\n")

    def _run(self):
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                logging.exception("Client task monitor failed; retrying")
            self._stop.wait(2)

    def poll_once(self):
        for task in self.state.list_tasks():
            if self._stop.is_set():
                return
            if task["status"] != "completed" or not task["result_cid"]:
                continue
            if task["download_status"] == "downloaded":
                continue
            if time.monotonic() < self._retry_after.get(task["task_id"], 0):
                continue
            loop = getattr(self.node, "loop", None)
            if not self.node.peers or loop is None or not loop.is_running():
                continue
            self._download(task)

    def _download(self, task):
        task_id = task["task_id"]
        staging = None
        future = None
        try:
            self.state.set_download(task_id, "downloading")
            output_dir = Path(task["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=".zyra-download-", dir=output_dir))
            archive = staging / "result.zip"
            workspace = staging / "workspace"
            workspace.mkdir()
            self.notify(f"\n[Client] Task {task_id} selesai. Mengunduh hasil ke {output_dir} ...")
            future = asyncio.run_coroutine_threadsafe(
                self.node.request_file(task["result_cid"], str(archive)), self.node.loop
            )
            self._download_future = future
            future.result(timeout=120)
            extract_workspace(archive, workspace)

            # Never overwrite existing user files, including after an interrupted download.
            result_path = output_dir / f"zyra_workspace_{task_id}"
            zip_path = output_dir / f"zyra_result_{task_id}.zip"
            if result_path.exists() or zip_path.exists():
                suffix = uuid.uuid4().hex[:8]
                result_path = output_dir / f"zyra_workspace_{task_id}_{suffix}"
                zip_path = output_dir / f"zyra_result_{task_id}_{suffix}.zip"
            os.rename(workspace, result_path)
            os.rename(archive, zip_path)
            self.state.set_download(task_id, "downloaded", result_path=result_path, zip_path=zip_path)
            self._retry_after.pop(task_id, None)
            self.notify(f"[Client] Hasil task {task_id} tersimpan!\n  Workspace: {result_path}\n  ZIP: {zip_path}\n")
        except Exception as exc:
            if future is not None:
                future.cancel()
            reason = str(exc) or type(exc).__name__
            self.state.set_download(task_id, "error", error=reason)
            self._retry_after[task_id] = time.monotonic() + 30
            if not self._stop.is_set() and (task["download_status"] != "error" or task["error"] != reason):
                self.notify(f"[Client] Hasil {task_id} belum berhasil diunduh: {reason}. "
                            "Akan dicoba lagi; node penyimpan hasil harus online.")
        finally:
            self._download_future = None
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
