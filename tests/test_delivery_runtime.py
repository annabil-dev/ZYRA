import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai.execution import runtime
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
    assert parsed == contract
    assert parse_submission("--web buat pemantau")[1]["profile"] == "flask-web"
    assert parse_submission("hitung fibonacci")[1]["profile"] == "python"


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
