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


def main():
    try:
        stage, contract_path = sys.argv[1:]
        contract = validate_contract(json.loads(Path(contract_path).read_text(encoding="utf-8")))
        root = Path.cwd()
        details = test_workspace(root) if stage == "unit" else smoke_workspace(root, contract)
        print(REPORT_PREFIX + json.dumps({"ok": True, "stage": stage, "details": details}))
        return 0
    except BaseException as exc:
        print(REPORT_PREFIX + json.dumps({"ok": False, "error": str(exc) or type(exc).__name__}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
