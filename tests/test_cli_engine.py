from types import SimpleNamespace
from unittest.mock import Mock

from zyra_cmd import installer
from zyra_cmd.client_state import ClientState


def test_zyra_data_dir_can_isolate_node_wallets_without_changing_python_appdata():
    import os
    from zyra_cmd.zyra_cli import get_zyra_data_dir

    appdata = r"C:\Users\test\AppData\Roaming"
    assert get_zyra_data_dir({"APPDATA": appdata}) == os.path.join(appdata, "ZYRA AI")

    custom = r"C:\Users\test\AppData\Local\ZYRA\miner-a"
    assert get_zyra_data_dir({"APPDATA": appdata, "ZYRA_DATA_DIR": custom}) == os.path.abspath(custom)


def test_retired_evm_commands_are_recognized_without_blocking_native_wallet_commands():
    from zyra_cmd.zyra_cli import is_retired_legacy_command

    assert is_retired_legacy_command("/link 0xabc")
    assert is_retired_legacy_command("/claim 10")
    assert is_retired_legacy_command("/deploy")
    assert not is_retired_legacy_command("/stake 2 mythvaloper1validator")
    assert not is_retired_legacy_command("/unstake 1 mythvaloper1validator")
    assert not is_retired_legacy_command("/send 2 MTC myth1recipient")


def missing_ollama(*args, **kwargs):
    raise FileNotFoundError("ollama")


def test_decline_is_remembered_across_restarts(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(installer, "is_ollama_running", lambda: False)
    monkeypatch.setattr(installer.subprocess, "run", missing_ollama)
    answer = Mock(return_value="n")
    monkeypatch.setattr("builtins.input", answer)

    assert not installer.check_and_install_ollama(ClientState(tmp_path))
    assert "/engine" in capsys.readouterr().out
    assert not installer.check_and_install_ollama(ClientState(tmp_path))
    answer.assert_called_once()
    assert "not installed" not in capsys.readouterr().out


def test_engine_explicitly_retries_install_after_decline(tmp_path, monkeypatch):
    state = ClientState(tmp_path)
    state.set_setting("ollama_install_prompted", True)
    running = Mock(side_effect=[False, True])
    monkeypatch.setattr(installer, "is_ollama_running", running)
    monkeypatch.setattr(installer.sys, "platform", "linux")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command == ["ollama", "--version"]:
            raise FileNotFoundError("ollama")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert installer.check_and_install_ollama(state, force_prompt=True)
    assert any(isinstance(cmd, str) and "install.sh" in cmd for cmd in calls)


def test_external_engine_is_detected_after_previous_decline(tmp_path, monkeypatch):
    state = ClientState(tmp_path)
    state.set_setting("ollama_install_prompted", True)
    monkeypatch.setattr(installer, "is_ollama_running", lambda: True)
    answer = Mock(side_effect=AssertionError("Must not prompt"))
    monkeypatch.setattr("builtins.input", answer)
    assert installer.check_and_install_ollama(ClientState(tmp_path))
    answer.assert_not_called()


def test_client_repl_engine_output_submit_and_history(tmp_path, monkeypatch, capsys):
    # Keep CLI import-time config and runtime wallets away from the user's files.
    from pathlib import Path
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("ZYRA_MYTHCHAIN_MODE", "off")
    monkeypatch.chdir(tmp_path)
    from zyra_cmd import zyra_cli
    from p2p import network

    class FakeNode:
        def __init__(self, **kwargs):
            self.peers = set()
            self.tasks = {}
            self.on_task_updated = None

        async def start(self):
            pass

        def add_task(self, payload):
            self.tasks[payload["task_id"]] = payload

    monkeypatch.setattr(network, "P2PNode", FakeNode)
    monkeypatch.setattr(zyra_cli, "PromptSession", None)
    monkeypatch.setattr(zyra_cli, "ZyraWallet", lambda _: SimpleNamespace(address="Z_TEST", metamask_address=None))
    monkeypatch.setattr(zyra_cli, "ZyraLedger", lambda _: None)
    engine_calls = []

    def configure(state, force_prompt=False):
        engine_calls.append(force_prompt)
        return force_prompt

    monkeypatch.setattr(installer, "check_and_install_ollama", configure)
    monkeypatch.setattr(installer, "check_and_pull_model", lambda _: "test-model")
    local_model = SimpleNamespace(model_name="test-model")
    monkeypatch.setattr(zyra_cli, "LocalLLMGenerator", lambda **kwargs: local_model)
    monkeypatch.setattr(zyra_cli.sys, "argv", ["zyra"])
    output = tmp_path / "My Client Results"
    commands = iter(["/engine", "/model changed-model", f'/output "{output}"',
                     "/submit create a calculator", "/tasks", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(commands))

    zyra_cli.main()

    assert engine_calls == [False, True]
    assert local_model.model_name == "changed-model"
    state = ClientState(tmp_path / "ZYRA AI")
    tasks = state.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["output_dir"] == str(output.resolve())
    assert tasks[0]["task_id"] in zyra_cli.p2p_node.tasks
    assert "output_dir" not in zyra_cli.p2p_node.tasks[tasks[0]["task_id"]]
    text = capsys.readouterr().out
    assert "Ollama siap" in text
    assert str(output) in text
