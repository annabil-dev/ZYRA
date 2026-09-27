import asyncio
import contextlib
import zipfile
from pathlib import Path

import pytest
import websockets

from p2p.network import P2PNode
from p2p.protocol import MessageType, create_message, parse_message
from p2p.votes import sign_vote
from ai.blockchain.wallet import ZyraWallet
from zyra_cmd.client_state import ClientState
from zyra_cmd.client_tasks import ClientTaskMonitor, extract_workspace


def test_output_preference_and_task_destination_survive_restart(tmp_path, monkeypatch):
    state = ClientState(tmp_path / "settings")
    first = tmp_path / "First Results"
    assert state.set_output_dir(f'"{first}"') == first.resolve()
    state.add_task({"task_id": "one", "status": "pending", "prompt": "Write code"})
    second = tmp_path / "Second Results"
    state.set_output_dir(str(second))
    monkeypatch.chdir(tmp_path)

    restored = ClientState(tmp_path / "settings")
    assert restored.get_output_dir() == second.resolve()
    assert restored.get_task("one")["output_dir"] == str(first.resolve())
    restored.add_task({"task_id": "two", "status": "pending"})
    assert restored.get_task("two")["output_dir"] == str(second.resolve())
    restored.update_from_network({"task_id": "one", "status": "completed",
                                  "result_cid": "CID", "output_dir": "untrusted"})
    restored.update_from_network({"task_id": "one", "status": "pending"})
    restored.update_from_network({"task_id": "someone-else", "status": "completed"})
    assert restored.get_task("one")["status"] == "completed"
    assert restored.get_task("one")["output_dir"] == str(first.resolve())
    assert restored.get_task("someone-else") is None


def test_invalid_output_keeps_previous_preference(tmp_path):
    state = ClientState(tmp_path / "state")
    output = state.set_output_dir(str(tmp_path / "results"))
    existing_file = tmp_path / "file.txt"
    existing_file.write_text("keep", encoding="utf-8")
    with pytest.raises(OSError):
        state.set_output_dir(str(existing_file))
    with pytest.raises(ValueError):
        state.set_output_dir('""')
    assert state.get_output_dir() == output
    assert existing_file.read_text(encoding="utf-8") == "keep"


async def wait_until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0.01)
    await asyncio.wait_for(wait(), timeout=5)


def test_offline_completion_recovered_via_real_peer_sync_and_download(tmp_path):
    """Restart client after miner completed; exercise actual WebSocket gossip/file transfer."""
    async def scenario():
        data_dir = tmp_path / "state"
        output = tmp_path / "client results"
        original = ClientState(data_dir)
        original.set_output_dir(str(output))
        original.add_task({"task_id": "task-one", "status": "pending", "prompt": "hello"})

        miner = P2PNode()
        miner.loop = asyncio.get_running_loop()
        miner_wallet = ZyraWallet(str(tmp_path / "miner-wallet"))
        miner.tasks["task-one"] = {"task_id": "task-one", "status": "validating", "acceptance_hash": "acceptance"}
        miner.trajectories["hash"] = {"task_id": "task-one", "trajectory_hash": "hash", "trajectory_log": "CID_ONE",
                                      "acceptance_hash": "acceptance", "miner_identity": miner_wallet.address,
                                      "miner_public_key": miner_wallet.public_key, "status": "pending_validation"}
        for judge_name in ("judge1", "judge2"):
            vote = sign_vote(ZyraWallet(str(tmp_path / judge_name)), miner.trajectories["hash"], "PASS")
            miner.add_signature(vote)
        source = tmp_path / "miner.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("src/hello.py", "print('hello')\n")
        miner.hosted_files["CID_ONE"] = str(source)

        restored = ClientState(data_dir)
        client = P2PNode()
        client.loop = asyncio.get_running_loop()
        client.on_task_updated = restored.update_from_network
        messages = []
        monitor = ClientTaskMonitor(restored, client, messages.append)

        async with websockets.serve(miner.handle_client, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            connection = asyncio.create_task(client.connect_to_peer(f"ws://127.0.0.1:{port}"))
            try:
                await wait_until(lambda: restored.get_task("task-one")["status"] == "completed")
                # A failed transfer stays recoverable, including across another restart.
                request_file = client.request_file

                async def temporarily_unavailable(*args):
                    raise ConnectionError("miner temporarily unavailable")

                client.request_file = temporarily_unavailable
                await asyncio.to_thread(monitor.poll_once)
                assert restored.get_task("task-one")["download_status"] == "error"
                client.request_file = request_file
                monitor = ClientTaskMonitor(ClientState(data_dir), client, messages.append)

                # Preserve any pre-existing user files in the nominal destination.
                existing = output / "zyra_workspace_task-one"
                existing.mkdir()
                (existing / "notes.txt").write_text("user work", encoding="utf-8")
                await asyncio.to_thread(monitor.poll_once)
                result = restored.get_task("task-one")
                assert result["download_status"] == "downloaded"
                assert Path(result["result_path"]).parent == output
                assert (Path(result["result_path"]) / "src/hello.py").read_text() == "print('hello')\n"
                assert Path(result["zip_path"]).is_file()
                assert (existing / "notes.txt").read_text() == "user work"
                assert not client.downloading_files
                assert not client.file_transfer_callbacks
                assert "output_dir" not in client.tasks["task-one"]

                # A future launch reports the path without downloading the same result again.
                messages.clear()
                restarted = ClientTaskMonitor(ClientState(data_dir), client, messages.append)
                restarted.show_tasks(startup=True)
                assert any(result["result_path"] in message for message in messages)

                async def must_not_download(*args):
                    pytest.fail("Completed downloads must not repeat")

                client.request_file = must_not_download
                await asyncio.to_thread(restarted.poll_once)
            finally:
                for peer in list(client.peers):
                    await peer.close()
                connection.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await connection

    asyncio.run(scenario())


def test_incremental_task_updates_are_persisted(tmp_path):
    async def scenario():
        state = ClientState(tmp_path)
        state.add_task({"task_id": "tracked", "status": "pending"})
        client = P2PNode()
        client.on_task_updated = state.update_from_network
        for status in ("mining", "validating"):
            raw = create_message(MessageType.TASK_UPDATED,
                                 {"task_id": "tracked", "status": status, "result_cid": "CID"})
            await client.handle_message(parse_message(raw), None, raw)
            assert ClientState(tmp_path).get_task("tracked")["status"] == status
        raw = create_message(MessageType.TASK_UPDATED, {"task_id": "tracked", "status": "completed", "result_cid": "fake"})
        await client.handle_message(parse_message(raw), None, raw)
        assert ClientState(tmp_path).get_task("tracked")["status"] == "validating"
    asyncio.run(scenario())


def test_cancelled_transfer_can_be_retried(tmp_path):
    async def scenario():
        node = P2PNode()
        node.loop = asyncio.get_running_loop()
        first = asyncio.create_task(node.request_file("CID", str(tmp_path / "first.zip")))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not node.downloading_files
        assert not node.file_transfer_callbacks
        retry = asyncio.create_task(node.request_file("CID", str(tmp_path / "retry.zip")))
        await asyncio.sleep(0)
        node.file_transfer_callbacks["CID"].set_result(True)
        assert await retry == str(tmp_path / "retry.zip")
        assert not node.downloading_files
    asyncio.run(scenario())


@pytest.mark.parametrize("filename", ["../escape.txt", "/escape.txt", "C:/escape.txt", "..\\escape.txt"])
def test_workspace_cannot_escape_selected_folder(tmp_path, filename):
    archive_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(filename, "bad")
    destination = tmp_path / "workspace"
    destination.mkdir()
    with pytest.raises(ValueError, match="Unsafe workspace path"):
        extract_workspace(archive_path, destination)
    assert list(destination.iterdir()) == []
