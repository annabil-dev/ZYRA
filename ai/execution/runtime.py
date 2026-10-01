"""One Docker runtime for miner commands and independent judge checks."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from .contract import RUNTIME, contract_hash, deliverable_files, validate_contract, validate_deliverables
from .scoring import score_acceptance

ASSETS = Path(__file__).resolve().parent
_build_lock = threading.Lock()
MAX_REQUIREMENTS_BYTES = 32 * 1024
MAX_REQUIREMENTS = 64
TASK_BUILDER_VERSION = "wheel-builder-v2"
PIP_CACHE_ID = "zyra-pip-wheels-v1"
BASE_BUILDER_VERSION = "base-builder-v2"


class RuntimeUnavailable(RuntimeError):
    pass


def image_name():
    digest = hashlib.sha256()
    digest.update(BASE_BUILDER_VERSION.encode("ascii"))
    digest.update(b"\0")
    digest.update(runtime_platform().encode("ascii"))
    digest.update(b"\0")
    for name in ("Dockerfile", "runtime-requirements.txt", "contract.py", "runner.py", "scoring.py"):
        digest.update((ASSETS / name).read_bytes())
    return "zyra-python-runtime:" + digest.hexdigest()[:16]


def runtime_platform():
    platform = os.environ.get("ZYRA_RUNTIME_PLATFORM", "linux/amd64").strip().lower()
    if platform not in {"linux/amd64", "linux/arm64"}:
        raise RuntimeUnavailable("ZYRA_RUNTIME_PLATFORM must be linux/amd64 or linux/arm64")
    return platform


def ensure_runtime():
    image = image_name()
    platform = runtime_platform()
    with _build_lock:
        try:
            subprocess.run(["docker", "info"], capture_output=True, text=True, check=True, timeout=20)
            buildx = subprocess.run(
                ["docker", "buildx", "version"], capture_output=True, text=True, check=False, timeout=20
            )
            if buildx.returncode != 0:
                raise RuntimeUnavailable(
                    "Docker Buildx is required for the pinned task runtime. Install the Docker Buildx plugin "
                    "(Ubuntu Docker CE package: docker-buildx-plugin), then verify with `docker buildx version`."
                )
            existing = subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=20)
            if existing.returncode == 0:
                details = _docker_image_info(image)
                if f"{details['os']}/{details['architecture']}" != platform:
                    subprocess.run(["docker", "image", "rm", image], capture_output=True, timeout=30)
                else:
                    return image
            print(f"[Runtime] Preparing {RUNTIME} (Flask + Chromium). First build requires internet...")
            subprocess.run(["docker", "build", "--platform", platform, "--provenance=false",
                            "--build-arg", "SOURCE_DATE_EPOCH=0", "--tag", image, str(ASSETS)],
                           check=True, timeout=900)
            return image
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeUnavailable("Docker runtime unavailable. Start Docker Desktop/Engine, then run /runtime. "
                                     f"Details: {exc}") from exc


def _task_requirements(workspace):
    """Read a small, pinned requirements manifest; reject pip options and URLs."""
    path = Path(workspace) / "requirements.txt"
    if not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeUnavailable(f"Dependency unavailable: cannot read requirements.txt: {exc}") from exc
    if len(raw.encode("utf-8")) > MAX_REQUIREMENTS_BYTES:
        raise RuntimeUnavailable("Dependency unavailable: requirements.txt exceeds 32 KiB")

    base_requirements = {}
    for base_line in (ASSETS / "runtime-requirements.txt").read_text(encoding="utf-8").splitlines():
        base_line = base_line.split("#", 1)[0].strip()
        if "==" in base_line:
            name, version = base_line.split("==", 1)
            base_requirements[re.sub(r"[-_.]+", "-", name).lower()] = version

    requirements = []
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(
            r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)", line
        )
        if not match or "*" in match.group(2):
            raise RuntimeUnavailable(
                "Dependency unavailable: requirements.txt must contain only exact package pins "
                f"in name==version form (line {line_number})"
            )
        name, version = match.groups()
        normalized_name = re.sub(r"[-_.]+", "-", name).lower()
        if base_requirements.get(normalized_name) == version:
            continue
        requirements.append(line)
        if len(requirements) > MAX_REQUIREMENTS:
            raise RuntimeUnavailable(f"Dependency unavailable: requirements.txt exceeds {MAX_REQUIREMENTS} packages")
    return "\n".join(requirements)


def _docker_image_info(image):
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{json .}}", image],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeUnavailable(f"Docker image unavailable ({image}): {(result.stderr or result.stdout).strip()}")
    try:
        raw = json.loads(result.stdout)
        layers = raw["RootFS"]["Layers"]
        return {
            "id": raw["Id"],
            "os": raw["Os"],
            "architecture": raw["Architecture"],
            "rootfs_sha256": hashlib.sha256(
                json.dumps(layers, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeUnavailable(f"Could not fingerprint Docker image {image}: {exc}") from exc


def _requirements_manifest_hash(workspace):
    path = Path(workspace) / "requirements.txt"
    raw = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = sorted(
        line.split("#", 1)[0].strip().lower()
        for line in raw.splitlines()
        if line.split("#", 1)[0].strip()
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _runtime_fingerprint(base_info, requirements_hash, packages):
    identity = {
        "builder": TASK_BUILDER_VERSION,
        "base_image_id": base_info["id"],
        "platform": f"{base_info['os']}/{base_info['architecture']}",
        "base_rootfs_sha256": base_info["rootfs_sha256"],
        "requirements_sha256": requirements_hash,
        "packages": sorted(packages, key=lambda p: (p["name"].lower(), p["version"], p["sha256"])),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), identity


def _task_runtime_name(runtime_fingerprint):
    return "zyra-python-task:" + runtime_fingerprint[:20]


def _bootstrap_runtime_name(base_info, requirements_hash):
    digest = hashlib.sha256()
    digest.update(base_info["id"].encode("utf-8"))
    digest.update(b"\0")
    digest.update(requirements_hash.encode("ascii"))
    digest.update(b"\0")
    digest.update(TASK_BUILDER_VERSION.encode("ascii"))
    return "zyra-python-bootstrap:" + digest.hexdigest()[:20]


def _parse_install_report(report_path):
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        entries = report["install"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeUnavailable(f"Dependency lock unavailable: invalid pip install report: {exc}") from exc
    packages = []
    for entry in entries:
        try:
            name = str(entry["metadata"]["name"])
            version = str(entry["metadata"]["version"])
            sha256 = entry["download_info"]["archive_info"]["hashes"].get("sha256")
        except (KeyError, TypeError) as exc:
            raise RuntimeUnavailable(f"Dependency lock unavailable: malformed wheel record: {exc}") from exc
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", version)
                or not re.fullmatch(r"[0-9a-f]{64}", str(sha256 or ""))):
            raise RuntimeUnavailable(f"Dependency lock unavailable: package {name!r} has no valid wheel SHA-256")
        packages.append({"name": name, "version": version, "sha256": sha256})
    packages.sort(key=lambda p: (p["name"].lower(), p["version"], p["sha256"]))
    if len(packages) > MAX_REQUIREMENTS * 4:
        raise RuntimeUnavailable("Dependency lock unavailable: resolved dependency closure exceeds 256 packages")
    return packages


def _locked_requirements(packages):
    return "\n".join(
        f"{package['name']}=={package['version']} --hash=sha256:{package['sha256']}"
        for package in packages
    )


def _read_workspace_manifest(workspace):
    path = Path(workspace) / "zyra.json"
    if not path.is_file():
        return path, None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeUnavailable(f"Runtime lock unavailable: cannot read zyra.json: {exc}") from exc
    if not isinstance(manifest, dict):
        raise RuntimeUnavailable("Runtime lock unavailable: zyra.json must contain a JSON object")
    return path, manifest


def _write_runtime_environment(manifest_path, manifest, metadata):
    if not manifest_path.is_file() or not isinstance(manifest, dict):
        return False
    manifest["runtime_environment"] = metadata
    temporary = manifest_path.with_name(manifest_path.name + ".zyra-tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, manifest_path)
    return True


def _validate_runtime_environment(metadata, base_info, requirements_hash, direct_requirements):
    if not isinstance(metadata, dict) or metadata.get("schema") != 1:
        raise RuntimeUnavailable("Runtime lock unavailable: zyra.json has no supported runtime_environment lock")
    if metadata.get("base_image_id") != base_info["id"]:
        raise RuntimeUnavailable("Runtime base-image ID differs from the Miner; refusing a different environment")
    if metadata.get("platform") != f"{base_info['os']}/{base_info['architecture']}":
        raise RuntimeUnavailable("Runtime platform differs from the Miner")
    if metadata.get("base_rootfs_sha256") != base_info["rootfs_sha256"]:
        raise RuntimeUnavailable("Runtime base filesystem fingerprint differs from the Miner")
    if metadata.get("requirements_sha256") != requirements_hash:
        raise RuntimeUnavailable("Runtime lock no longer matches requirements.txt")

    packages = metadata.get("packages")
    if not isinstance(packages, list) or len(packages) > MAX_REQUIREMENTS * 4:
        raise RuntimeUnavailable("Runtime lock has an invalid package list")
    normalized = {}
    for package in packages:
        if not isinstance(package, dict):
            raise RuntimeUnavailable("Runtime lock contains a malformed package entry")
        name, version, sha256 = package.get("name"), package.get("version"), package.get("sha256")
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)
                or not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", version)
                or not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256)):
            raise RuntimeUnavailable("Runtime lock contains an invalid package pin or wheel hash")
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in normalized and normalized[key] != (version, sha256):
            raise RuntimeUnavailable(f"Runtime lock contains conflicting pins for {name}")
        normalized[key] = (version, sha256)
    for line in direct_requirements.splitlines():
        name, version = line.split("==", 1)
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key not in normalized or normalized[key][0] != version:
            raise RuntimeUnavailable(f"Runtime lock does not cover required package {name}=={version}")

    fingerprint, _ = _runtime_fingerprint(base_info, requirements_hash, packages)
    if metadata.get("fingerprint") != fingerprint:
        raise RuntimeUnavailable("Runtime fingerprint does not match the base image and wheel lock")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(metadata.get("task_image_id", ""))):
        raise RuntimeUnavailable("Runtime lock has no valid OCI image ID")
    if not re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("task_rootfs_sha256", ""))):
        raise RuntimeUnavailable("Runtime lock has no valid task filesystem fingerprint")
    return fingerprint, packages


def _build_task_image(base_image, task_image, requirements, *, locked=False):
    with tempfile.TemporaryDirectory(prefix="zyra-dependency-build-") as build_dir:
        context = Path(build_dir)
        (context / "requirements.txt").write_text(requirements + "\n", encoding="utf-8")
        install_options = (
            "--no-deps --require-hashes --only-binary=:all:"
            if locked else "--only-binary=:all:"
        )
        report_option = "" if locked else "--report /opt/zyra/task-install-report.json "
        (context / "Dockerfile").write_text(
            "# syntax=docker/dockerfile:1.7\n"
            f"FROM {base_image}\n"
            "COPY requirements.txt /opt/zyra/task-requirements.txt\n"
            f"RUN --mount=type=cache,id={PIP_CACHE_ID},target=/root/.cache/pip,sharing=locked "
            "python -m pip install --disable-pip-version-check --cache-dir=/root/.cache/pip "
            f"--index-url https://pypi.org/simple {install_options} "
            f"{report_option}-r /opt/zyra/task-requirements.txt "
            "&& rm /opt/zyra/task-requirements.txt\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            ["docker", "build", "--platform", runtime_platform(), "--provenance=false",
             "--build-arg", "SOURCE_DATE_EPOCH=0", "--network", "default",
             "--resource", "memory=1g", "--resource", "cpu-quota=100000",
             "--tag", task_image, str(context)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "dependency image build failed").strip()[-4000:]
            raise RuntimeUnavailable(f"Dependency unavailable: {detail}")


def _install_report_from_image(image):
    name = "zyra-dependency-report-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="zyra-dependency-report-") as temp_dir:
        report_path = Path(temp_dir) / "install-report.json"
        try:
            created = subprocess.run(["docker", "create", "--name", name, image],
                                     capture_output=True, text=True, timeout=30)
            if created.returncode != 0:
                raise RuntimeUnavailable(f"Dependency lock unavailable: {created.stderr[-2000:]}")
            copied = subprocess.run(
                ["docker", "cp", f"{name}:/opt/zyra/task-install-report.json", str(report_path)],
                capture_output=True, text=True, timeout=30,
            )
            if copied.returncode != 0:
                raise RuntimeUnavailable(f"Dependency lock unavailable: {copied.stderr[-2000:]}")
            return _parse_install_report(report_path)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeUnavailable(f"Dependency lock unavailable: {exc}") from exc
        finally:
            subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=20)


def _prune_task_runtime_cache(keep_image):
    try:
        max_images = int(os.environ.get("ZYRA_TASK_RUNTIME_CACHE_MAX", "8"))
    except ValueError:
        max_images = 8
    if not 1 <= max_images <= 64:
        max_images = 8
    try:
        listed = subprocess.run(
            ["docker", "image", "ls", "--filter", "reference=zyra-python-task:*",
             "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True, text=True, timeout=20,
        )
        if listed.returncode != 0:
            return
        images = [image.strip() for image in listed.stdout.splitlines() if image.strip()]
        if len(images) <= max_images:
            return

        created = []
        for image in images:
            inspected = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{.Created}}", image],
                capture_output=True, text=True, timeout=20,
            )
            if inspected.returncode == 0:
                created.append((inspected.stdout.strip(), image))
        for _, image in sorted(created):
            if len(images) <= max_images:
                break
            if image == keep_image:
                continue
            removed = subprocess.run(["docker", "image", "rm", image],
                                     capture_output=True, text=True, timeout=30)
            if removed.returncode == 0:
                images.remove(image)
    except (OSError, subprocess.SubprocessError):
        # Cache cleanup must never turn a successfully prepared runtime into failure.
        return


def prepare_task_runtime(workspace, base_image, *, require_runtime_lock=False):
    """Prepare a pinned, wheel-hash-locked image for a Miner or independent Judge.

    First-time Miner preparation resolves binary wheels in a disposable Builder,
    records every wheel SHA-256 in zyra.json, then creates the canonical Runner
    image from that lock. A Judge requires this lock and refuses a different base
    runtime or platform. App/test containers never receive the Builder cache/network.
    """
    direct_requirements = _task_requirements(workspace)
    requirements_hash = _requirements_manifest_hash(workspace)
    base_info = _docker_image_info(base_image)
    manifest_path, manifest = _read_workspace_manifest(workspace)
    metadata = manifest.get("runtime_environment") if manifest else None

    if metadata is not None:
        if not isinstance(metadata, dict):
            if require_runtime_lock:
                raise RuntimeUnavailable("Runtime lock in zyra.json is malformed")
            metadata = None
    if metadata is not None:
        if (metadata.get("base_image_id") != base_info["id"]
                or metadata.get("requirements_sha256") != requirements_hash):
            if require_runtime_lock:
                raise RuntimeUnavailable("Runtime lock does not match the Miner base image or requirements")
            metadata = None

    if metadata is not None:
        try:
            fingerprint, packages = _validate_runtime_environment(
                metadata, base_info, requirements_hash, direct_requirements
            )
        except RuntimeUnavailable:
            if require_runtime_lock:
                raise
            metadata = None
    if metadata is not None:
        task_image = _task_runtime_name(fingerprint)
        try:
            task_info = _docker_image_info(task_image)
        except RuntimeUnavailable:
            if not packages:
                task_image = base_image
                task_info = base_info
            else:
                _build_task_image(base_image, task_image, _locked_requirements(packages), locked=True)
                task_info = _docker_image_info(task_image)
        expected_rootfs = metadata.get("task_rootfs_sha256")
        if expected_rootfs and task_info["rootfs_sha256"] != expected_rootfs:
            raise RuntimeUnavailable(
                "Prepared task image filesystem differs from the Miner runtime lock; refusing Judge execution"
            )
        if task_info["id"] != metadata.get("task_image_id"):
            raise RuntimeUnavailable(
                "Prepared OCI image ID differs from the Miner runtime lock; refusing Judge execution"
            )
        _prune_task_runtime_cache(task_image)
        return task_image

    packages = []
    bootstrap_image = base_image
    if direct_requirements:
        bootstrap_image = _bootstrap_runtime_name(base_info, requirements_hash)
        existing = subprocess.run(["docker", "image", "inspect", bootstrap_image],
                                  capture_output=True, text=True, timeout=20)
        if existing.returncode != 0:
            _build_task_image(base_image, bootstrap_image, direct_requirements, locked=False)

    if manifest is None:
        if require_runtime_lock and direct_requirements:
            raise RuntimeUnavailable("Runtime lock manifest missing from task artifact")
        if require_runtime_lock:
            return base_image
        # Early Coder commands may run before it has written zyra.json. Keep the
        # resolver image cached; final delivery validation binds its lock.
        return bootstrap_image

    if require_runtime_lock and direct_requirements:
        raise RuntimeUnavailable("Runtime lock missing from Miner artifact; refusing unpinned Judge execution")

    if direct_requirements:
        packages = _install_report_from_image(bootstrap_image)
        resolved = {re.sub(r"[-_.]+", "-", p["name"]).lower(): p["version"] for p in packages}
        for line in direct_requirements.splitlines():
            name, version = line.split("==", 1)
            key = re.sub(r"[-_.]+", "-", name).lower()
            if resolved.get(key) != version:
                raise RuntimeUnavailable(f"Dependency lock does not resolve requested pin {line}")

    fingerprint, identity = _runtime_fingerprint(base_info, requirements_hash, packages)
    task_image = _task_runtime_name(fingerprint) if packages else base_image
    if packages:
        existing = subprocess.run(["docker", "image", "inspect", task_image],
                                  capture_output=True, text=True, timeout=20)
        if existing.returncode != 0:
            _build_task_image(base_image, task_image, _locked_requirements(packages), locked=True)
        task_info = _docker_image_info(task_image)
        _prune_task_runtime_cache(task_image)
    else:
        task_info = base_info

    metadata = {
        "schema": 1,
        **identity,
        "fingerprint": fingerprint,
        "task_image_id": task_info["id"],
        "task_rootfs_sha256": task_info["rootfs_sha256"],
    }
    if not _write_runtime_environment(manifest_path, manifest, metadata):
        raise RuntimeUnavailable("Runtime lock could not be stored in zyra.json")

    if direct_requirements:
        subprocess.run(["docker", "image", "rm", bootstrap_image], capture_output=True, timeout=30)
    return task_image


def docker_command(workspace, image, name, command, contract_dir=None):
    user = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "1000:1000"
    args = ["docker", "run", "--rm", "--name", name, "--platform", runtime_platform(),
            "--network", "none", "--memory", "1g",
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
    task_image = prepare_task_runtime(workspace, image)
    return run_container(workspace, task_image, ["sh", "-c", command], timeout=60)


def validate_workspace(workspace, acceptance, *, require_runtime_lock=False):
    report = {"status": "FAILED", "runtime": RUNTIME, "stages": [], "retry": True}
    try:
        contract = validate_contract(acceptance)
        report["acceptance_hash"] = contract_hash(contract)
        validate_deliverables(workspace, contract)
        image = prepare_task_runtime(workspace, ensure_runtime(), require_runtime_lock=require_runtime_lock)
        validate_deliverables(workspace, contract)
        report["image"] = image
        locked_manifest = json.loads((Path(workspace) / "zyra.json").read_text(encoding="utf-8"))
        runtime_environment = locked_manifest.get("runtime_environment", {})
        report["runtime_fingerprint"] = runtime_environment.get("fingerprint")
        if contract.get("criteria"):
            with tempfile.TemporaryDirectory(prefix="zyra_criteria_") as directory:
                root = Path(directory) / "criteria"
                root.mkdir()
                for name in deliverable_files(workspace):
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(Path(workspace) / name, target)
                config_dir = Path(directory) / "contract"
                config_dir.mkdir()
                (config_dir / "acceptance.json").write_text(json.dumps(contract), encoding="utf-8")
                result = run_container(root, image, ["python", "-I", "/opt/zyra/runner.py", "criteria",
                                                     "/zyra-contract/acceptance.json"], contract_dir=config_dir)
                if result.returncode in (125, 126, 127):
                    raise RuntimeUnavailable(f"Container could not execute the judge: {result.stderr[-2000:]}")
                entries = [line[len("ZYRA_RUNTIME_REPORT="):]
                           for line in result.stdout.splitlines()
                           if line.startswith("ZYRA_RUNTIME_REPORT=")]
                details = json.loads(entries[-1]) if entries else {
                    "ok": False, "error": "Criteria runner produced no report", "unavailable": True,
                }
                report["stages"].append({"stage": "criteria", **details})
                if details.get("unavailable"):
                    raise RuntimeUnavailable(details.get("error", "Judge criteria runtime unavailable"))
                if result.returncode != 0 or not details.get("ok"):
                    report.update(reason=details.get("error", "Criteria checks could not be evaluated"),
                                  stdout=result.stdout[-4000:], stderr=result.stderr[-4000:])
                    return False, report
                criteria_results = details.get("details", {}).get("criteria_results")
                score = score_acceptance(contract["criteria"], criteria_results)
                report.update(
                    criteria_results=criteria_results,
                    acceptance_score=score,
                    client_report_markdown=score["client_report_markdown"],
                    delivery_ready=True,
                )
                if score["status"] == "PASSED":
                    report.update(status="PASSED", reason="Weighted acceptance criteria passed.", retry=False)
                    return True, report
                report.update(status="FAILED", reason="Weighted acceptance score did not meet the task pass policy.", retry=True)
                return False, report
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
    valid, report = validate_workspace(args.workspace, acceptance, require_runtime_lock=True)
    print(json.dumps(report, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
