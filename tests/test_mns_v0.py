import json

import pytest

from zyra_cmd.mns_v0 import format_result, load_registry, normalize_name, resolve_name


def test_normalizes_ascii_myth_names():
    assert normalize_name(" RPC.Mythchain.Myth. ") == "rpc.mythchain.myth"


@pytest.mark.parametrize("name", ["", "myth", "a..myth", "-bad.myth", "bad-.myth",
                                   "bad_name.myth", "é.myth", "host.example.com"])
def test_rejects_invalid_names(name):
    with pytest.raises(ValueError):
        normalize_name(name)


def test_resolves_bundled_local_alias_and_marks_it_noncanonical():
    result = resolve_name("RPC.MYTHCHAIN.MYTH")
    assert result["scope"] == "local-static"
    assert {item["type"]: item["value"] for item in result["records"]}["RPC"] == "http://127.0.0.1:26657"
    assert "not resolved by public DNS or Mythchain state" in format_result(result)


def test_custom_registry_normalizes_keys_and_returns_none_for_missing(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"version": 0, "scope": "local-static",
                                "names": {"TEST.MYTH": [{"type": "A", "value": "127.0.0.2", "ttl": 30}]}}),
                    encoding="utf-8")
    registry = load_registry(path)
    assert resolve_name("test.myth", registry)["records"][0]["value"] == "127.0.0.2"
    assert resolve_name("missing.myth", registry)["records"] is None


def test_rejects_invalid_record_ttl(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"version": 0, "scope": "local-static",
                                "names": {"test.myth": [{"type": "A", "value": "127.0.0.1", "ttl": -1}]}}),
                    encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid record fields"):
        load_registry(path)
