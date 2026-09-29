"""Trusted runtime checks, copied into the image, never supplied by a miner."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract import validate_contract

REPORT_PREFIX = "ZYRA_RUNTIME_REPORT="


def test_workspace(root):
    sys.path.insert(0, str(root))
    suite = unittest.defaultTestLoader.discover(str(root), pattern="test*.py", top_level_dir=str(root))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.testsRun == 0 or result.testsRun == len(result.skipped):
        raise RuntimeError(f"Unit tests failed or no tests ran: run={result.testsRun}, skipped={len(result.skipped)}")
    return {"tests_run": result.testsRun, "skipped": len(result.skipped)}


def application_command(root, contract):
    return [sys.executable, str(root / contract["entrypoint"]), *contract["args"]]


def application_environment(contract):
    env = os.environ.copy()
    env.update({"PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1", "HOST": "0.0.0.0",
                "PORT": str(contract.get("port", 8000)), "FLASK_DEBUG": "0"})
    return env


def check_http(base_url, check):
    opener = build_opener(ProxyHandler({}))
    try:
        response = opener.open(base_url + check["path"], timeout=5)
    except HTTPError as exc:
        response = exc
    with response:
        body = response.read(2 * 1024 * 1024).decode("utf-8")
        if response.status != check.get("status", 200):
            raise RuntimeError(f"{check['path']}: expected HTTP {check.get('status', 200)}, got {response.status}")
        if check.get("content_type") and check["content_type"] not in response.headers.get("Content-Type", ""):
            raise RuntimeError(f"{check['path']}: incorrect Content-Type")
        for text in check.get("contains", []):
            if text not in body:
                raise RuntimeError(f"{check['path']}: missing expected text {text!r}")
        if check.get("json_keys") or "json_equals" in check:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise RuntimeError(f"{check['path']}: expected a JSON object")
            for key in check.get("json_keys", []):
                if key not in data:
                    raise RuntimeError(f"{check['path']}: missing JSON field {key}")
            for key, expected in check.get("json_equals", {}).items():
                if key not in data or data[key] != expected:
                    raise RuntimeError(f"{check['path']}: unexpected value for {key}")
        return {"path": check["path"], "status": response.status}


def check_browser(base_url, contract):
    from playwright.sync_api import sync_playwright
    errors = []
    api_paths = set()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.on("requestfailed", lambda request: errors.append(f"Request failed: {request.url}"))

            def received(response):
                path = urlparse(response.url).path
                if response.status >= 400 and path != "/favicon.ico":
                    errors.append(f"Browser HTTP {response.status}: {response.url}")
                if response.request.resource_type in {"fetch", "xhr"} and response.ok:
                    api_paths.add(path)

            page.on("response", received)
            # Ignore the browser's implicit favicon request; it is not an application feature.
            page.route("**/favicon.ico", lambda route: route.fulfill(status=204))
            page.goto(base_url + "/", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(1000)
            visible_text = page.locator("body").inner_text().strip()
            if not visible_text:
                errors.append("The home page has no visible content")
            for text in contract["browser_contains"]:
                if text not in visible_text:
                    errors.append(f"Browser did not display expected text: {text!r}")
            for check in contract["http_checks"]:
                if check.get("browser_fetch") and urlparse(check["path"]).path not in api_paths:
                    errors.append(f"Frontend did not successfully fetch {check['path']}")
            if errors:
                raise RuntimeError("Browser checks failed: " + "; ".join(errors[:10]))
            return {"browser": "chromium", "api_paths": sorted(api_paths), "page_errors": 0}
        finally:
            browser.close()


def stop_application(process):
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=3)


def smoke_workspace(root, contract):
    command = application_command(root, contract)
    env = application_environment(contract)
    if contract["profile"] == "python":
        result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise RuntimeError(f"Application exited with {result.returncode}: {result.stderr[-2000:]}")
        for text in contract["stdout_contains"]:
            if text not in result.stdout:
                raise RuntimeError(f"Application stdout is missing {text!r}")
        return {"exit_code": result.returncode, "stdout": result.stdout[-2000:]}

    base_url = f"http://127.0.0.1:{contract['port']}"
    with tempfile.TemporaryFile(mode="w+b") as log:
        process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=log,
                                   start_new_session=(os.name != "nt"))
        try:
            opener = build_opener(ProxyHandler({}))
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Web application exited before readiness (code {process.returncode})")
                try:
                    with opener.open(base_url + "/", timeout=1):
                        break
                except (URLError, OSError):
                    time.sleep(0.1)
            else:
                raise RuntimeError("Web application did not become ready within 15 seconds")
            checks = [check_http(base_url, check) for check in contract["http_checks"]]
            browser = check_browser(base_url, contract)
            if process.poll() is not None:
                raise RuntimeError("Web application stopped during validation")
            return {"http": checks, **browser}
        except Exception as exc:
            log.seek(0)
            output = log.read().decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"{exc}\nApplication log:\n{output}") from exc
        finally:
            stop_application(process)


def _criterion_outcome(passed, evidence):
    evidence = str(evidence).strip() or "No check evidence was produced"
    return {"passed": bool(passed), "evidence": evidence[:1000]}


def evaluate_browser_criteria(base_url, criteria):
    """Run browser criteria in one isolated Chromium session."""
    results = {}
    checks = [(criterion, criterion["check"]) for criterion in criteria
              if criterion["check"]["type"] in {"browser_contains", "browser_fetch"}]
    if not checks:
        return results

    from playwright.sync_api import sync_playwright

    fetched = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.on("requestfailed", lambda request: errors.append(f"Request failed: {request.url}"))

            def received(response):
                parsed = urlparse(response.url)
                if response.request.resource_type in {"fetch", "xhr"}:
                    fetched[parsed.path] = response.status

            page.on("response", received)
            page.route("**/favicon.ico", lambda route: route.fulfill(status=204))
            page.goto(base_url + "/", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(500)
            visible_text = page.locator("body").inner_text().strip()
            for criterion, check in checks:
                if check["type"] == "browser_contains":
                    expected = check["text"]
                    found = expected in visible_text
                    evidence = (f"Browser displayed expected text: {expected!r}" if found
                                else f"Browser did not display expected text: {expected!r}")
                    if errors:
                        evidence += "; browser errors: " + "; ".join(errors[:3])
                    results[criterion["id"]] = _criterion_outcome(found, evidence)
                else:
                    path = urlparse(check["path"]).path
                    status = fetched.get(path)
                    passed = status is not None and status < 400
                    evidence = (f"Browser fetched {path} with HTTP {status}" if passed
                                else f"Browser did not successfully fetch {path}; observed status={status}")
                    if errors:
                        evidence += "; browser errors: " + "; ".join(errors[:3])
                    results[criterion["id"]] = _criterion_outcome(passed, evidence)
        finally:
            browser.close()
    return results


def evaluate_criteria(root, contract):
    """Execute the client-declared, machine-readable weighted criteria."""
    criteria = contract.get("criteria", [])
    if not criteria:
        return {}
    results = {}
    checks = [(criterion, criterion["check"]) for criterion in criteria]
    profile = contract["profile"]

    if profile == "python":
        process_result = None
        needs_process = any(check["type"] in {"application_runs", "stdout_contains"} for _, check in checks)
        if needs_process:
            try:
                process_result = subprocess.run(
                    application_command(root, contract), cwd=root, env=application_environment(contract),
                    capture_output=True, text=True, timeout=15,
                )
            except Exception as exc:
                process_result = exc
        for criterion, check in checks:
            if check["type"] == "application_runs":
                passed = isinstance(process_result, subprocess.CompletedProcess) and process_result.returncode == 0
                evidence = ("Application exited successfully" if passed else
                            f"Application did not exit successfully: {process_result}")
            else:
                stdout = process_result.stdout if isinstance(process_result, subprocess.CompletedProcess) else ""
                passed = process_result is not None and not isinstance(process_result, Exception) and process_result.returncode == 0 and check["text"] in stdout
                evidence = (f"stdout contains {check['text']!r}" if passed else
                            f"stdout is missing {check['text']!r}; output: {stdout[-500:]}")
            results[criterion["id"]] = _criterion_outcome(passed, evidence)
        return results

    command = application_command(root, contract)
    env = application_environment(contract)
    base_url = f"http://127.0.0.1:{contract['port']}"
    with tempfile.TemporaryFile(mode="w+b") as log:
        process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=log,
                                   start_new_session=(os.name != "nt"))
        try:
            opener = build_opener(ProxyHandler({}))
            deadline = time.monotonic() + 15
            ready = False
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    with opener.open(base_url + "/", timeout=1):
                        ready = True
                        break
                except (URLError, OSError):
                    time.sleep(0.1)

            for criterion, check in checks:
                criterion_id = criterion["id"]
                if check["type"] == "application_runs":
                    passed = ready and process.poll() is None
                    evidence = "Web application started and remained active" if passed else "Web application did not become ready"
                elif not ready:
                    passed = False
                    evidence = "Web application did not become ready for this check"
                elif check["type"] == "http":
                    try:
                        check_http(base_url, {key: value for key, value in check.items() if key != "type"})
                        passed, evidence = True, f"HTTP acceptance check passed for {check['path']}"
                    except Exception as exc:
                        passed, evidence = False, str(exc)
                else:
                    continue
                results[criterion_id] = _criterion_outcome(passed, evidence)

            try:
                results.update(evaluate_browser_criteria(base_url, criteria))
            except Exception as exc:
                raise RuntimeError(f"Judge browser runtime unavailable: {exc}") from exc
            return results
        except RuntimeError:
            log.seek(0)
            output = log.read().decode("utf-8", errors="replace")[-1000:]
            raise
        finally:
            stop_application(process)


def main():
    try:
        stage, contract_path = sys.argv[1:]
        contract = validate_contract(json.loads(Path(contract_path).read_text(encoding="utf-8")))
        root = Path.cwd()
        if stage == "unit":
            details = test_workspace(root)
        elif stage == "smoke":
            details = smoke_workspace(root, contract)
        elif stage == "criteria":
            details = {"criteria_results": evaluate_criteria(root, contract)}
        else:
            raise ValueError(f"Unknown validation stage: {stage}")
        print(REPORT_PREFIX + json.dumps({"ok": True, "stage": stage, "details": details}))
        return 0
    except RuntimeError as exc:
        print(REPORT_PREFIX + json.dumps({"ok": False, "unavailable": True,
                                          "error": str(exc) or type(exc).__name__}))
        return 1
    except BaseException as exc:
        print(REPORT_PREFIX + json.dumps({"ok": False, "error": str(exc) or type(exc).__name__}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
