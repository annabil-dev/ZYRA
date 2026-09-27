import asyncio
import base64
import hashlib
from pathlib import Path

import pytest

from p2p.content import content_cid, is_sha256_cid, verify_content_cid
from p2p.network import P2PNode
from p2p.protocol import MessageType, create_message, parse_message


def test_content_cid_is_stable_and_checks_entire_file(tmp_path):
    artifact = tmp_path / "workspace.zip"
    artifact.write_bytes(b"workspace archive bytes")
    expected = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert content_cid(artifact) == expected
    assert is_sha256_cid(expected)
    assert verify_content_cid(artifact, expected) == expected
    assert not is_sha256_cid("P2P_LOCAL_legacy")
    assert verify_content_cid(artifact, "P2P_LOCAL_legacy") is None


def test_seed_rejects_cid_that_does_not_match_file(tmp_path):
    artifact = tmp_path / "result.zip"
    artifact.write_bytes(b"original")
    cid = content_cid(artifact)
    node = P2PNode()
    node.seed_file(cid, artifact)
    artifact.write_bytes(b"mutated")
    with pytest.raises(ValueError, match="digest mismatch"):
        node.seed_file(cid, artifact)
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_content_cid(artifact, cid)


def test_receiver_verifies_assembled_file_before_resolving_download(tmp_path):
    async def scenario(payload, expected_cid, should_pass):
        node = P2PNode()
        node.loop = asyncio.get_running_loop()
        destination = tmp_path / ("valid.zip" if should_pass else "tampered.zip")
        future = node.loop.create_future()
        node.downloading_files[expected_cid] = {"chunks": {}, "path": str(destination), "size": 0}
        node.file_transfer_callbacks[expected_cid] = future
        for index, offset in enumerate(range(0, len(payload), 65536)):
            chunk = payload[offset:offset + 65536]
            message = create_message(MessageType.FILE_CHUNK, {
                "cid": expected_cid,
                "chunk_index": index,
                "data": base64.b64encode(chunk).decode("ascii")
            })
            await node.handle_message(parse_message(message), None, message)
        eof = create_message(MessageType.FILE_CHUNK, {"cid": expected_cid, "chunk_index": -1, "data": ""})
        await node.handle_message(parse_message(eof), None, eof)
        if should_pass:
            assert await future is True
            assert destination.read_bytes() == payload
        else:
            with pytest.raises(ValueError, match="digest mismatch"):
                await future
            assert not destination.exists()

    async def run():
        valid = b"verified workspace payload"
        cid = content_cid_from_bytes(valid)
        await scenario(valid, cid, True)
        await scenario(b"tampered workspace payload", cid, False)
    asyncio.run(run())


def content_cid_from_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def test_legacy_opaque_cid_still_transfers_without_integrity_claim(tmp_path):
    async def scenario():
        node = P2PNode()
        node.loop = asyncio.get_running_loop()
        cid = "P2P_LOCAL_legacy"
        payload = b"legacy payload"
        destination = tmp_path / "legacy.zip"
        node.downloading_files[cid] = {"chunks": {0: payload}, "path": str(destination), "size": len(payload)}
        future = node.loop.create_future()
        node.file_transfer_callbacks[cid] = future
        eof = create_message(MessageType.FILE_CHUNK, {"cid": cid, "chunk_index": -1, "data": ""})
        await node.handle_message(parse_message(eof), None, eof)
        assert await future is True
        assert destination.read_bytes() == payload
    asyncio.run(scenario())
