"""One Docker runtime for miner commands and independent judge checks."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from .contract import RUNTIME, contract_hash, deliverable_files, validate_contract, validate_deliverables

ASSETS = Path(__file__).resolve().parent
_build_lock = threading.Lock()


class RuntimeUnavailable(RuntimeError):
    pass


def image_name():
    digest = hashlib.sha256()
    for name in ("Dockerfile", "runtime-requirements.txt", "contract.py", "runner.py"):
        digest.update((ASSETS / name).read_bytes())
    return "zyra-python-runtime:" + digest.hexdigest()[:16]


def ensure_runtime():
    image = image_name()
    with _build_lock:
        try:
            subprocess.run(["docker", "info"], capture_output=True, text=True, check=True, timeout=20)
            existing = subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=20)
            if existing.returncode == 0:
                return image
            print(f"[Runtime] Preparing {RUNTIME} (Flask + Chromium). First build requires internet...")
            subprocess.run(["docker", "build", "--tag", image, str(ASSETS)], check=True, timeout=900)
            return image
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeUnavailable("Docker runtime unavailable. Start Docker Desktop/Engine, then run /runtime. "
                                     f"Details: {exc}") from exc


def docker_command(workspace, image, name, command, contract_dir=None):
    user = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "1000:1000"
    args = ["docker", "run", "--rm", "--name", name, "--network", "none", "--memory", "1g",
            "--cpus", "1", "--pids-limit", "256", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--read-only", "--user", user,
            "--tmpfs", "/tmp:rw,size=256m", "--shm-size", "256m",
            "-v", f"{Path(workspace).resolve()}:/app", "-w", "/app"]
    if contract_dir is not None:
        args.extend(["-v", f"{Path(contract_dir).resolve()}:/zyra-contract:ro"])
    return [*args, image, *command]


def run_container(workspace, image, command, timeout=90, contract_dir=None):
    name = "zyra-task-" + uuid.uuid4().hex
    try:
        return subprocess.run(docker_command(workspace, image, name, command, contract_dir),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    finally:
        # Killing the docker client on timeout alone would leave a running container.
        try:
            subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            pass


def execute_miner_command(workspace, command, image):
    return run_container(workspace, image, ["sh", "-c", command], timeout=60)


def validate_workspace(workspace, acceptance):
    report = {"status": "FAILED", "runtime": RUNTIME, "stages": [], "retry": True}
    try:
        contract = validate_contract(acceptance)
        report["acceptance_hash"] = contract_hash(contract)
        validate_deliverables(workspace, contract)
        image = ensure_runtime()
        report["image"] = image
        with tempfile.TemporaryDirectory(prefix="zyra_verify_") as directory:
            base = Path(directory)
            config_dir = base / "contract"
            config_dir.mkdir()
            (config_dir / "acceptance.json").write_text(json.dumps(contract), encoding="utf-8")
            for stage in ("unit", "smoke"):
                # Independent copies prevent tests from replacing the app before startup checks.
                root = base / stage
                root.mkdir()
                for name in deliverable_files(workspace):
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(Path(workspace) / name, target)
                result = run_container(root, image, ["python", "-I", "/opt/zyra/runner.py", stage,
                                                     "/zyra-contract/acceptance.json"], contract_dir=config_dir)
                if result.returncode in (125, 126, 127):
                    raise RuntimeUnavailable(f"Container could not execute the judge: {result.stderr[-2000:]}")
                entries = [line[len("ZYRA_RUNTIME_REPORT="):] for line in result.stdout.splitlines()
                           if line.startswith("ZYRA_RUNTIME_REPORT=")]
                details = json.loads(entries[-1]) if entries else {"ok": False, "error": "Runner produced no report"}
                report["stages"].append({"stage": stage, **details})
                if result.returncode != 0 or not details.get("ok"):
                    report.update(reason=f"{stage} failed: {details.get('error', 'process failed')}",
                                  stdout=result.stdout[-4000:], stderr=result.stderr[-4000:])
                    return False, report
        report.update(status="PASSED", reason="Documentation, unit tests, and real application checks passed.", retry=False)
        return True, report
    except RuntimeUnavailable as exc:
        report.update(status="UNAVAILABLE", reason=str(exc), retry=False)
    except Exception as exc:
        report["reason"] = str(exc) or type(exc).__name__
    return False, report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Verify a ZYRA delivery using the shared Docker judge runtime")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--contract", required=True, type=Path, help="Original client acceptance JSON")
    args = parser.parse_args()
    acceptance = json.loads(args.contract.read_text(encoding="utf-8"))
    valid, report = validate_workspace(args.workspace, acceptance)
    print(json.dumps(report, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
