"""Client-owned acceptance criteria. No code from the submitted workspace is imported."""

import hashlib
import json
import re
import shlex
from pathlib import Path, PurePosixPath

try:
    from .scoring import validate_criteria
except ImportError:  # Trusted runtime imports contract.py as a standalone module.
    from scoring import validate_criteria

RUNTIME = "zyra-python-v1"
PROFILES = {"python", "flask-web"}
IGNORED_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules"}
CRITERION_CHECK_TYPES = {"application_runs", "stdout_contains", "http", "browser_contains", "browser_fetch"}


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("Use a relative workspace path with forward slashes")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValueError(f"Invalid workspace path: {value}")
    return value


def validate_criterion_check(check, profile):
    if (not isinstance(check, dict) or not isinstance(check.get("type"), str)
            or check.get("type") not in CRITERION_CHECK_TYPES):
        raise ValueError(f"criterion check type must be one of {sorted(CRITERION_CHECK_TYPES)}")
    if len(json.dumps(check, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > 16 * 1024:
        raise ValueError("criterion check JSON cannot exceed 16 KiB")
    check_type = check["type"]
    if check_type == "application_runs":
        if set(check) != {"type"}:
            raise ValueError("application_runs criterion check only accepts type")
        return
    if check_type == "stdout_contains":
        if profile != "python" or set(check) != {"type", "text"}:
            raise ValueError("stdout_contains criteria require a python profile and only type/text fields")
        if (not isinstance(check["text"], str) or not check["text"].strip()
                or len(check["text"].encode("utf-8")) > 1000):
            raise ValueError("stdout_contains criterion text must contain 1 to 1000 characters")
        return
    if check_type == "browser_contains":
        if profile != "flask-web" or set(check) != {"type", "text"}:
            raise ValueError("browser_contains criteria require flask-web and only type/text fields")
        if (not isinstance(check["text"], str) or not check["text"].strip()
                or len(check["text"].encode("utf-8")) > 1000):
            raise ValueError("browser_contains criterion text must contain 1 to 1000 characters")
        return
    if check_type == "browser_fetch":
        if profile != "flask-web" or set(check) != {"type", "path"}:
            raise ValueError("browser_fetch criteria require flask-web and only type/path fields")
        path = check["path"]
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or "#" in path:
            raise ValueError("browser_fetch criterion path must be a local path starting with /")
        return

    allowed = {"type", "path", "status", "content_type", "contains", "json_keys", "json_equals"}
    if profile != "flask-web" or set(check) - allowed or not isinstance(check.get("path"), str):
        raise ValueError("http criterion checks require flask-web and supported HTTP assertion fields")
    path = check["path"]
    if not path.startswith("/") or path.startswith("//") or "#" in path:
        raise ValueError("HTTP criterion paths must be local paths starting with /")
    if not isinstance(check.get("status", 200), int) or not 200 <= check.get("status", 200) <= 599:
        raise ValueError("Invalid HTTP criterion status")
    if not isinstance(check.get("content_type", ""), str):
        raise ValueError("HTTP criterion content_type must be text")
    for field in ("contains", "json_keys"):
        values = check.get(field, [])
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ValueError(f"HTTP criterion {field} must be a list of strings")
    if "json_equals" in check and not isinstance(check["json_equals"], dict):
        raise ValueError("HTTP criterion json_equals must be an object")


def validate_contract(value):
    contract = json.loads(json.dumps(value))
    if not isinstance(contract, dict) or contract.get("version") != 1:
        raise ValueError("Acceptance contract version must be 1")
    unknown = set(contract) - {"version", "runtime", "profile", "entrypoint", "args", "port",
                               "http_checks", "stdout_contains", "browser_contains", "criteria"}
    if unknown:
        raise ValueError(f"Unknown acceptance fields: {sorted(unknown)}")
    if contract.get("runtime") != RUNTIME or contract.get("profile") not in PROFILES:
        raise ValueError("Supported profiles: python and flask-web, runtime zyra-python-v1")
    relative_path(contract.get("entrypoint"))
    if not contract["entrypoint"].endswith(".py"):
        raise ValueError("Entrypoint must be a Python file")
    args = contract.setdefault("args", [])
    if not isinstance(args, list) or len(args) > 20 or not all(isinstance(a, str) for a in args):
        raise ValueError("args must be a list of strings")
    checks = contract.setdefault("http_checks", [])
    if not isinstance(checks, list) or len(checks) > 20:
        raise ValueError("http_checks must be a list of at most 20 checks")
    if contract["profile"] == "flask-web":
        if not isinstance(contract.get("port"), int) or not 1024 <= contract["port"] <= 65535:
            raise ValueError("Web port must be between 1024 and 65535")
        if not checks or not any(c.get("path") == "/" for c in checks if isinstance(c, dict)):
            raise ValueError("Web contracts must check the home page /")
    elif checks:
        raise ValueError("HTTP checks require the flask-web profile")
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError("Each HTTP check must be an object")
        unknown = set(check) - {"path", "status", "content_type", "contains", "json_keys", "json_equals", "browser_fetch"}
        if unknown:
            raise ValueError(f"Unknown HTTP check fields: {sorted(unknown)}")
        path = check.get("path", "")
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or "#" in path:
            raise ValueError("HTTP check paths must be local paths starting with /")
        if not isinstance(check.get("status", 200), int) or not 200 <= check.get("status", 200) <= 599:
            raise ValueError("Invalid expected HTTP status")
        if not isinstance(check.get("content_type", ""), str):
            raise ValueError("content_type must be a string")
        for field in ("contains", "json_keys"):
            if not isinstance(check.get(field, []), list) or not all(isinstance(x, str) for x in check.get(field, [])):
                raise ValueError(f"{field} must be a list of strings")
        if "json_equals" in check and not isinstance(check["json_equals"], dict):
            raise ValueError("json_equals must be an object of expected top-level fields")
        if not isinstance(check.get("browser_fetch", False), bool):
            raise ValueError("browser_fetch must be a boolean")
    output = contract.setdefault("stdout_contains", [])
    if not isinstance(output, list) or not all(isinstance(s, str) for s in output):
        raise ValueError("stdout_contains must be a list of strings")
    visible = contract.setdefault("browser_contains", [])
    if not isinstance(visible, list) or not all(isinstance(s, str) for s in visible):
        raise ValueError("browser_contains must be a list of strings")
    if contract["profile"] == "python" and visible:
        raise ValueError("browser_contains requires flask-web")
    if "criteria" in contract:
        contract["criteria"] = validate_criteria(contract["criteria"])
        for criterion in contract["criteria"]:
            if "check" not in criterion:
                raise ValueError(f"Criterion {criterion['id']} needs a machine-executable check")
            validate_criterion_check(criterion["check"], contract["profile"])
    return contract


def make_contract(prompt, web=False):
    web = web or bool(re.search(r"\b(web|website|flask|dashboard|frontend|backend|html|http)\b", prompt, re.I))
    contract = {"version": 1, "runtime": RUNTIME, "profile": "flask-web" if web else "python",
                "entrypoint": "app.py" if web else "main.py", "args": [], "http_checks": []}
    if web:
        contract["port"] = 8000
        contract["http_checks"] = [{"path": "/", "status": 200, "content_type": "text/html", "contains": ["<html"]}]
    return validate_contract(contract)


def contract_hash(contract):
    payload = json.dumps(validate_contract(contract), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def startup_command(contract):
    return shlex.join(["python", contract["entrypoint"], *contract["args"]])


def _ensure_weighted_criteria(contract, prompt, generator=None):
    if contract.get("criteria"):
        return validate_contract(contract)
    from .criterion_generator import generate_criteria
    criteria, _source = generate_criteria(prompt, contract["profile"], generator=generator)
    contract["criteria"] = criteria
    return validate_contract(contract)


def parse_submission(text, criterion_generator=None):
    """Preserve Windows paths and prompt quoting; only parse leading CLI options."""
    text = text.strip()
    if text.startswith("--spec "):
        match = re.match(r'''--spec\s+(?:"([^"]+)"|'([^']+)'|(\S+))\s+(.+)''', text, re.S)
        if not match:
            raise ValueError('/submit --spec "acceptance.json" <task>')
        path = next(part for part in match.groups()[:3] if part is not None)
        contract = validate_contract(json.loads(Path(path).expanduser().read_text(encoding="utf-8")))
        prompt = match.group(4).strip()
        contract = _ensure_weighted_criteria(contract, prompt, generator=criterion_generator)
        return prompt, contract
    web = text.startswith("--web ")
    if web:
        text = text[len("--web "):].strip()
    if not text or text.startswith("--"):
        raise ValueError("Use /submit [--web | --spec <file>] <task>")
    contract = make_contract(text, web=web)
    contract = _ensure_weighted_criteria(contract, text, generator=criterion_generator)
    return text, contract


def deliverable_files(root):
    root = Path(root)
    for file in sorted(root.rglob("*")):
        relative = file.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts) or file.suffix == ".pyc":
            continue
        if file.is_symlink():
            raise ValueError(f"Workspace symlinks are not supported: {relative}")
        if file.is_file():
            yield relative.as_posix()


def validate_deliverables(root, contract):
    root = Path(root)
    contract = validate_contract(contract)
    # Collect every issue in one pass instead of failing on the first one, so
    # the planner can fix the whole manifest in a single round (one rejection
    # per cycle otherwise burns a full swarm cycle per missing field).
    issues = []
    for name in ("README.md", "requirements.txt", "zyra.json", "test_suite.py", contract["entrypoint"]):
        if not (root / name).is_file():
            issues.append(f"Missing required deliverable: {name}")
    manifest = None
    if (root / "zyra.json").is_file():
        try:
            manifest = json.loads((root / "zyra.json").read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            issues.append(f"zyra.json is not valid JSON: {exc}")
    if isinstance(manifest, dict):
        for key in ("runtime", "profile", "entrypoint"):
            if manifest.get(key) != contract[key]:
                issues.append(f"zyra.json {key} does not match the client's contract")
        if manifest.get("acceptance_hash") != contract_hash(contract):
            issues.append("zyra.json acceptance_hash does not match the client's contract")
        expected_command = startup_command(contract)
        if manifest.get("run_command") != expected_command:
            issues.append(f"Document run_command as: {expected_command}")
        files = manifest.get("files")
        if not isinstance(files, dict):
            issues.append("zyra.json must describe each deliverable in files")
            files = None
    else:
        if manifest is not None:
            issues.append("zyra.json must be a JSON object")
        files = None
    readme = ""
    if (root / "README.md").is_file():
        try:
            readme = (root / "README.md").read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(f"README.md is not readable: {exc}")
    for heading in ("Setup", "Run", "Test", "Files", "Limitations"):
        if not re.search(r"^##\s+" + heading + r"\s*$", readme, re.M | re.I):
            issues.append(f"README.md needs a '## {heading}' section")
    try:
        expected_command = startup_command(contract)
    except Exception:
        expected_command = ""
    if expected_command and (expected_command not in readme or "python -m unittest discover" not in readme):
        issues.append("README.md must contain the actual run and test commands")
    workspace_files = []
    if files is not None:
        try:
            workspace_files = list(deliverable_files(root))
        except ValueError as exc:
            issues.append(str(exc))
    for name in workspace_files:
        if not isinstance(files.get(name), str) or not files[name].strip() or name not in readme:
            issues.append(f"Document the purpose of {name} in zyra.json and README.md")
    if files is not None:
        for name in files:
            try:
                relative_path(name)
            except Exception as exc:
                issues.append(f"zyra.json has an invalid file path {name!r}: {exc}")
                continue
            if not (root / name).is_file():
                issues.append(f"zyra.json describes a missing file: {name}")
    # Task dependencies are prepared in a separate builder from exact binary-wheel pins.
    # The app/test containers themselves remain offline.
    requirement_pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*==[A-Za-z0-9][A-Za-z0-9.!+_-]*\Z")
    try:
        requirements_text = (root / "requirements.txt").read_text(encoding="utf-8")
    except OSError as exc:
        requirements_text = ""
        if not any("Missing required deliverable: requirements.txt" in issue for issue in issues):
            issues.append(f"requirements.txt is not readable: {exc}")
    if len(requirements_text.encode("utf-8")) > 32 * 1024:
        issues.append("requirements.txt exceeds the 32 KiB runtime limit")
    dependencies = set()
    for line_number, raw_line in enumerate(requirements_text.splitlines(), start=1):
        requirement = raw_line.split("#", 1)[0].strip()
        if requirement:
            if not requirement_pattern.fullmatch(requirement) or "*" in requirement:
                issues.append(
                    "requirements.txt must use exact package==version pins supported by the isolated "
                    f"wheel builder (line {line_number})"
                )
            else:
                dependencies.add(requirement.lower())
                if len(dependencies) > 64:
                    issues.append("requirements.txt exceeds the 64 dependency runtime limit")
    if contract["profile"] == "flask-web" and "flask==3.1.3" not in dependencies:
        issues.append("Web deliverables must declare Flask==3.1.3")
    if issues:
        raise ValueError(
            f"{len(issues)} deliverable issue(s) must be fixed in one round:\n- " + "\n- ".join(issues)
        )
    return manifest


def delivery_instructions(contract):
    contract = validate_contract(contract)
    return f"""DELIVERY CONTRACT (client-owned; do not weaken or replace it):
{json.dumps(contract, indent=2)}
Acceptance hash: {contract_hash(contract)}
Runtime {RUNTIME}: Python 3.11, standard library, real Flask 3.1.3; task commands/tests run without internet.
Additional dependencies must be exact `package==version` pins in requirements.txt. ZYRA prepares a
cached, isolated task image using binary wheels before execution; do not run pip install yourself.
The builder cannot use source distributions, direct URLs, editable installs, or unpinned requirements.
Do not fake libraries, replace the application's runtime with mocks, or skip failing tests.
For flask-web: use real Flask; start via `{startup_command(contract)}`, read PORT from the environment
(default {contract.get('port', 8000)}), listen on 0.0.0.0, debug=False, use_reloader=False.
Use local frontend assets only. The judge opens a real Chromium browser and rejects JS/network errors.
For python: the entrypoint must terminate successfully without interactive input; use the contract args.
Always provide test_suite.py AND run all test*.py using `python -m unittest discover -v`.
Always provide requirements.txt (Flask==3.1.3 for web; empty/comment-only for standard-library scripts).
Always provide README.md with headings ## Setup, ## Run, ## Test, ## Files, ## Limitations.
Document installation, exact startup command, port/URL, test command, all file purposes, and any dummy data.
Always provide zyra.json with runtime, profile, entrypoint copied from the contract, acceptance_hash,
run_command (exactly {startup_command(contract)!r}), and files (every deliverable path -> purpose).
List README.md and zyra.json themselves too. Do not write verification claims without running the app.
The judge checks real startup and client HTTP/output expectations independently of your unit tests.
If the client contract includes weighted criteria, do not remove or change them. Report evidence and
known failures for every criterion; hard-gate criteria must pass for the task to pass.
If the isolated wheel builder cannot prepare a required dependency, report that exact error instead of
producing fake substitutes or claiming the tests passed.
"""
