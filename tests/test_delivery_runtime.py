import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai.execution import runner, runtime
from ai.execution.contract import (contract_hash, deliverable_files, make_contract,
                                   parse_submission, validate_contract, validate_deliverables)


def document(root, contract):
    (root / "requirements.txt").write_text("Flask==3.1.3\n" if contract["profile"] == "flask-web" else "# Standard library\n")
    (root / "README.md").touch()
    (root / "zyra.json").touch()
    files = {name: f"Purpose of {name}" for name in deliverable_files(root)}
    command = "python " + contract["entrypoint"]
    manifest = {key: contract[key] for key in ("runtime", "profile", "entrypoint")}
    manifest.update(acceptance_hash=contract_hash(contract), run_command=command, files=files)
    (root / "zyra.json").write_text(json.dumps(manifest))
    (root / "README.md").write_text(
        "## Setup\nInstall requirements.txt\n## Run\n" + command +
        "\n## Test\npython -m unittest discover -v\n## Files\n" +
        "\n".join(files) + "\n## Limitations\nTest fixture.\n")


def make_web_workspace(root, *, broken_js=False, mock=False):
    contract = make_contract("web dashboard")
    contract["browser_contains"] = ["Online"]
    contract["http_checks"].append({"path": "/api/status", "content_type": "application/json",
                                    "json_equals": {"status": "Online"}, "browser_fetch": True})
    html = "<html><body><h1>Status</h1><div id='status'></div><script>"
    html += "missingFunction();" if broken_js else "fetch('/api/status').then(r=>r.json()).then(d=>document.getElementById('status').textContent=d.status);"
    html += "</script></body></html>"
    if mock:
        source = "class FakeFlask: pass\napp = FakeFlask()\nif __name__ == '__main__': app.run()\n"
    else:
        source = ("import os\nfrom flask import Flask, jsonify\napp = Flask(__name__)\n"
                  f"@app.route('/')\ndef home(): return {html!r}\n"
                  "@app.route('/api/status')\ndef status(): return jsonify(status='Online')\n"
                  "if __name__ == '__main__': app.run(host='0.0.0.0', port=int(os.environ['PORT']), use_reloader=False)\n")
    (root / "app.py").write_text(source)
    # Deliberately weak miner tests: the independent runtime must still catch a broken app.
    (root / "test_suite.py").write_text("import unittest\nclass Test(unittest.TestCase):\n def test_pass(self): self.assertTrue(True)\n")
    document(root, contract)
    return contract


def test_client_contract_cannot_be_weakened_in_manifest(tmp_path):
    contract = make_web_workspace(tmp_path)
    validate_deliverables(tmp_path, contract)
    weaker = make_contract("web")
    document(tmp_path, weaker)
    with pytest.raises(ValueError, match="acceptance_hash"):
        validate_deliverables(tmp_path, contract)


def test_readme_and_each_file_must_be_documented(tmp_path):
    contract = make_web_workspace(tmp_path)
    (tmp_path / "extra.py").write_text("print('extra')")
    with pytest.raises(ValueError, match="extra.py"):
        validate_deliverables(tmp_path, contract)
    document(tmp_path, contract)
    (tmp_path / "README.md").write_text("It works, trust me")
    valid, report = runtime.validate_workspace(tmp_path, contract)
    assert not valid and "Setup" in report["reason"]


def test_unsupported_dependencies_fail_instead_of_mock_substitutes(tmp_path):
    contract = make_web_workspace(tmp_path)
    (tmp_path / "requirements.txt").write_text("Flask==3.1.3\nnonexistent-framework==1.0\n")
    valid, report = runtime.validate_workspace(tmp_path, contract)
    assert not valid and "Dependency unavailable" in report["reason"]


def test_missing_docker_never_executes_workspace_on_host(tmp_path, monkeypatch):
    contract = make_web_workspace(tmp_path)
    monkeypatch.setattr(runtime, "ensure_runtime", Mock(side_effect=runtime.RuntimeUnavailable("Docker unavailable")))
    execute = Mock(side_effect=AssertionError("Must not execute on host"))
    monkeypatch.setattr(runtime, "run_container", execute)
    valid, report = runtime.validate_workspace(tmp_path, contract)
    assert not valid and report["status"] == "UNAVAILABLE"
    execute.assert_not_called()


def test_submit_spec_keeps_client_checks_and_windows_paths(tmp_path):
    contract = make_contract("web")
    contract["http_checks"].append({"path": "/api/value", "json_equals": {"value": 42}})
    path = tmp_path / "my acceptance.json"
    path.write_text(json.dumps(contract))
    prompt, parsed = parse_submission(f'--spec "{path}" Build my dashboard')
    assert prompt == "Build my dashboard"
    assert parsed["profile"] == contract["profile"]
    assert parsed["criteria"]
    assert parse_submission("--web buat pemantau")[1]["profile"] == "flask-web"
    assert parse_submission("hitung fibonacci")[1]["profile"] == "python"


def test_client_prompt_automatically_generates_executable_weighted_criteria():
    class Generator:
        def generate(self, **kwargs):
            generated = json.dumps({"criteria": [
                {"id": "app-runs", "description": "Application runs", "weight": 20,
                 "hard_gate": True, "check": {"type": "application_runs"}},
                {"id": "home-page", "description": "Home route works", "weight": 80,
                 "hard_gate": True, "check": {"type": "http", "path": "/", "status": 200}},
            ]})
            yield generated, generated, {}

    prompt, contract = parse_submission("--web build a status dashboard", criterion_generator=Generator())

    assert prompt == "build a status dashboard"
    assert [criterion["id"] for criterion in contract["criteria"]] == ["app-runs", "home-page"]
    assert contract["criteria"][1]["check"]["path"] == "/"


def test_prompt_fallback_extracts_explicit_browser_text_and_endpoint_checks():
    _, contract = parse_submission("--web build dashboard that shows 'Online' and exposes /api/status")

    checks = {criterion["id"]: criterion["check"] for criterion in contract["criteria"]}
    assert checks["visible-text-1"] == {"type": "browser_contains", "text": "Online"}
    assert checks["endpoint-1"] == {"type": "http", "path": "/api/status", "status": 200}


def test_weighted_criterion_contract_runs_checks_and_returns_per_criterion_evidence(tmp_path):
    contract = make_contract("print a result")
    contract["criteria"] = [
        {"id": "starts", "description": "Program runs", "weight": 40, "hard_gate": True,
         "check": {"type": "application_runs"}},
        {"id": "answer", "description": "Prints the answer", "weight": 60, "hard_gate": False,
         "check": {"type": "stdout_contains", "text": "42"}},
    ]
    contract = validate_contract(contract)
    (tmp_path / "main.py").write_text("print('42')\n")

    results = runner.evaluate_criteria(tmp_path, contract)

    assert results["starts"]["passed"] is True
    assert results["answer"]["passed"] is True
    assert "stdout contains" in results["answer"]["evidence"]


def test_weighted_criterion_runner_reports_noncritical_failure(tmp_path):
    contract = make_contract("print a result")
    contract["criteria"] = [{
        "id": "expected-output", "description": "Print expected text", "weight": 100,
        "hard_gate": False, "check": {"type": "stdout_contains", "text": "expected"},
    }]
    contract = validate_contract(contract)
    (tmp_path / "main.py").write_text("print('different')\n")

    result = runner.evaluate_criteria(tmp_path, contract)["expected-output"]

    assert result["passed"] is False
    assert "missing" in result["evidence"]


def test_weighted_criteria_require_executable_task_checks():
    contract = make_contract("print a result")
    contract["criteria"] = [{
        "id": "unexecutable", "description": "Must do the thing", "weight": 100,
        "hard_gate": False,
    }]
    with pytest.raises(ValueError, match="machine-executable check"):
        validate_contract(contract)


def test_weighted_runtime_returns_partial_score_report_for_judge(tmp_path, monkeypatch):
    contract = make_web_workspace(tmp_path)
    contract["criteria"] = [
        {"id": "home", "description": "Home page works", "weight": 60, "hard_gate": True,
         "check": {"type": "application_runs"}},
        {"id": "api-extra", "description": "Extra API works", "weight": 40, "hard_gate": False,
         "check": {"type": "browser_contains", "text": "Extra"}},
    ]
    document(tmp_path, contract)
    outcomes = {
        "home": {"passed": True, "evidence": "Application started"},
        "api-extra": {"passed": False, "evidence": "Browser did not display Extra"},
    }
    details = {"ok": True, "stage": "criteria", "details": {"criteria_results": outcomes}}
    monkeypatch.setattr(runtime, "ensure_runtime", lambda: "test-image")
    monkeypatch.setattr(runtime, "run_container", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout="ZYRA_RUNTIME_REPORT=" + json.dumps(details) + "\n", stderr=""))

    valid, report = runtime.validate_workspace(tmp_path, contract)

    assert valid is False
    assert report["status"] == "FAILED"
    assert report["delivery_ready"] is True
    assert report["criteria_results"] == outcomes
    assert report["acceptance_score"]["criteria_score_percent"] == 60
    assert "api-extra" in report["client_report_markdown"]


@pytest.fixture
def docker_runtime():
    if os.environ.get("ZYRA_TEST_DOCKER") != "1":
        pytest.skip("Set ZYRA_TEST_DOCKER=1 for real container/browser integration tests")
    return runtime.ensure_runtime()


def test_real_flask_http_and_browser_pass(tmp_path, docker_runtime):
    contract = make_web_workspace(tmp_path)
    valid, report = runtime.validate_workspace(tmp_path, contract)
    assert valid, report
    assert report["stages"][1]["details"]["api_paths"] == ["/api/status"]


def test_real_weighted_http_and_browser_criteria_are_scored(tmp_path, docker_runtime):
    contract = make_web_workspace(tmp_path)
    contract["criteria"] = [
        {"id": "home-http", "description": "Home page responds", "weight": 40, "hard_gate": True,
         "check": {"type": "http", "path": "/", "status": 200, "contains": ["<html"]}},
        {"id": "status-visible", "description": "Client sees live status", "weight": 30,
         "hard_gate": False, "check": {"type": "browser_contains", "text": "Online"}},
        {"id": "status-fetch", "description": "Browser fetches status API", "weight": 30,
         "hard_gate": True, "check": {"type": "browser_fetch", "path": "/api/status"}},
    ]
    contract = validate_contract(contract)
    document(tmp_path, contract)

    valid, report = runtime.validate_workspace(tmp_path, contract)

    assert valid, report
    assert report["acceptance_score"]["criteria_score_percent"] == 100
    assert report["acceptance_score"]["hard_gate_passed"] is True
    assert set(report["criteria_results"]) == {"home-http", "status-visible", "status-fetch"}


@pytest.mark.parametrize("mode", ["mock", "broken_js", "wrong_api", "missing_display", "test_rewrites_app"])
def test_passing_unit_tests_do_not_hide_broken_app(tmp_path, docker_runtime, mode):
    contract = make_web_workspace(tmp_path, mock=(mode in {"mock", "test_rewrites_app"}),
                                  broken_js=(mode == "broken_js"))
    if mode == "wrong_api":
        (tmp_path / "app.py").write_text((tmp_path / "app.py").read_text().replace("status='Online'", "status='Wrong'"))
    if mode == "missing_display":
        (tmp_path / "app.py").write_text((tmp_path / "app.py").read_text().replace("textContent=d.status", "textContent='nothing'"))
    if mode == "test_rewrites_app":
        (tmp_path / "test_suite.py").write_text(
            "import unittest\nfrom pathlib import Path\nclass Test(unittest.TestCase):\n"
            " def test_replace_app(self):\n  Path('app.py').write_text(\"print('replaced')\")\n  self.assertTrue(True)\n")
    document(tmp_path, contract)
    original = (tmp_path / "app.py").read_text()
    valid, report = runtime.validate_workspace(tmp_path, contract)
    assert not valid, report
    assert report["stages"][0]["ok"], report
    assert report["stages"][1]["stage"] == "smoke" and not report["stages"][1]["ok"], report
    assert (tmp_path / "app.py").read_text() == original


def test_judge_discovers_failing_tests_outside_test_suite(tmp_path, docker_runtime):
    contract = make_web_workspace(tmp_path)
    (tmp_path / "test_other.py").write_text("import unittest\nclass Test(unittest.TestCase):\n def test_fail(self): self.fail('broken feature')\n")
    document(tmp_path, contract)
    valid, report = runtime.validate_workspace(tmp_path, contract)
    assert not valid and report["stages"][0]["stage"] == "unit", report


def test_script_requires_successful_real_entrypoint(tmp_path, docker_runtime):
    contract = make_contract("calculate a value")
    contract["stdout_contains"] = ["42"]
    (tmp_path / "main.py").write_text("print(6 * 7)\n")
    (tmp_path / "test_suite.py").write_text("import unittest\nclass Test(unittest.TestCase):\n def test_math(self): self.assertEqual(6*7,42)\n")
    document(tmp_path, contract)
    valid, report = runtime.validate_workspace(tmp_path, contract)
    assert valid, report
    (tmp_path / "main.py").write_text("raise RuntimeError('does not run')\n")
    valid, report = runtime.validate_workspace(tmp_path, contract)
    assert not valid and report["stages"][-1]["stage"] == "smoke", report


def test_false_done_does_not_submit_or_reward(tmp_path, monkeypatch):
    from zyra_cmd import zyra_cli
    contract = make_contract("calculate")
    node = SimpleNamespace(tasks={"job": {"acceptance": contract, "acceptance_hash": contract_hash(contract)}},
                           add_trajectory=Mock(), seed_file=Mock())
    monkeypatch.setattr(zyra_cli, "p2p_node", node, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime, "ensure_runtime", lambda: "test-image")
    monkeypatch.setattr(runtime, "validate_workspace", lambda *args: (False, {"reason": "Application cannot start"}))
    planner_calls = 0

    class Generator:
        def generate(self, **kwargs):
            nonlocal planner_calls
            if kwargs["override_model"] == "planner":
                planner_calls += 1
                text = "<DELEGATE>Write code</DELEGATE>" if planner_calls == 1 else "<ALL_DONE>"
            else:
                text = '<WRITE_FILE path="main.py">\nprint(42)\n</WRITE_FILE>\n[STEP_COMPLETE]'
            yield text, text, {}

    ledger = SimpleNamespace(add_pouw_reward=Mock())
    wallet = SimpleNamespace(address="Z_TEST", metamask_address=None)
    assert zyra_cli.run_automode(Generator(), "calculate", [], wallet, ledger, "model",
                                planner_model="planner", coder_model="coder", task_id="job") is False
    node.add_trajectory.assert_not_called()
    node.seed_file.assert_not_called()
    ledger.add_pouw_reward.assert_not_called()


def test_delivery_rejection_is_sent_to_coder_and_inspect_only_step_is_rejected(tmp_path, monkeypatch):
    from zyra_cmd import zyra_cli

    contract = make_contract("calculate")
    node = SimpleNamespace(tasks={"job": {"acceptance": contract,
                                            "acceptance_hash": contract_hash(contract)}})
    monkeypatch.setattr(zyra_cli, "p2p_node", node, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime, "ensure_runtime", lambda: "test-image")
    monkeypatch.setattr(runtime, "validate_workspace", lambda *args: (
        False, {"reason": "zyra.json acceptance_hash does not match the client's contract"}))
    coder_history = []
    planner_calls = 0
    coder_calls = 0

    class Generator:
        def generate(self, **kwargs):
            nonlocal planner_calls, coder_calls
            if kwargs["override_model"] == "planner":
                planner_calls += 1
                if planner_calls == 1:
                    text = "<DELEGATE>Make the initial files</DELEGATE>"
                elif planner_calls == 2:
                    text = "<ALL_DONE>"
                elif planner_calls == 3:
                    text = "<DELEGATE>Fix the validator report in the manifest</DELEGATE>"
                else:
                    text = "<ALL_DONE>"
            else:
                coder_calls += 1
                coder_history.append(list(kwargs["history"]))
                if coder_calls == 1:
                    text = "[STEP_COMPLETE]"
                elif coder_calls == 2:
                    text = "<CMD>cat zyra.json</CMD>\n[STEP_COMPLETE]"
                else:
                    text = '<WRITE_FILE path="zyra.json">{}\n</WRITE_FILE>\n[STEP_COMPLETE]'
            yield text, text, {}

    wallet = SimpleNamespace(address="Z_MINER", signing_address="Z_SIGNING", metamask_address=None)
    ledger = SimpleNamespace(add_pouw_reward=Mock())
    result = zyra_cli.run_automode(Generator(), "calculate", [], wallet, ledger, "model",
                                   planner_model="planner", coder_model="coder", task_id="job")

    assert result is False
    assert planner_calls == 15
    assert any(any("acceptance_hash does not match" in message.get("content", "")
                   for message in history if message.get("role") == "user")
               for history in coder_history)
    audit = next(tmp_path.joinpath("sandbox_workspace", "_audit").glob("*.jsonl"))
    assert "coder_fix_completion_rejected" in audit.read_text(encoding="utf-8")
