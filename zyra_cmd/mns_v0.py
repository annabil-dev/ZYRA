"""Local-only static MNS v0 lookup; it does not modify or query system DNS."""

import json
import os
import re
from pathlib import Path


DEFAULT_REGISTRY = Path(__file__).with_name("mns_v0.json")
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_name(value):
    """Return the canonical ASCII .myth name or raise ValueError."""
    if not isinstance(value, str):
        raise ValueError("Name must be text")
    name = value.strip()
    if name.endswith("."):
        name = name[:-1]
    try:
        name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("MNS v0 only supports ASCII names") from exc
    name = name.lower()
    if len(name) > 253 or not name.endswith(".myth"):
        raise ValueError("Name must end in .myth and be at most 253 characters")
    labels = name.split(".")
    if len(labels) < 2 or any(not _LABEL.fullmatch(label) for label in labels):
        raise ValueError("Name contains an invalid label")
    return name


def load_registry(path=None):
    """Load and validate a local static registry JSON file."""
    registry_path = Path(path or os.environ.get("ZYRA_MNS_V0_FILE", DEFAULT_REGISTRY))
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read local MNS registry: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Local MNS registry is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != 0 or payload.get("scope") != "local-static":
        raise ValueError("Registry must declare version 0 and scope local-static")
    names = payload.get("names")
    if not isinstance(names, dict):
        raise ValueError("Registry names must be an object")
    canonical = {}
    for raw_name, records in names.items():
        name = normalize_name(raw_name)
        if name in canonical:
            raise ValueError(f"Duplicate canonical name: {name}")
        if not isinstance(records, list) or len(records) > 32:
            raise ValueError(f"Records for {name} must be a list of at most 32 entries")
        validated = []
        for record in records:
            if not isinstance(record, dict) or set(record) != {"type", "value", "ttl"}:
                raise ValueError(f"Invalid record for {name}: expected type, value, and ttl")
            record_type = record["type"]
            value = record["value"]
            ttl = record["ttl"]
            if (not isinstance(record_type, str) or not record_type.isascii()
                    or not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024
                    or not isinstance(ttl, int) or isinstance(ttl, bool) or not 0 <= ttl <= 86400):
                raise ValueError(f"Invalid record fields for {name}")
            validated.append({"type": record_type.upper(), "value": value, "ttl": ttl})
        canonical[name] = validated
    return {"version": 0, "scope": "local-static", "notice": payload.get("notice", ""), "names": canonical}


def resolve_name(value, registry=None):
    """Look up a name in the local registry; return None when absent."""
    name = normalize_name(value)
    loaded = registry if registry is not None else load_registry()
    return {"name": name, "scope": loaded["scope"], "records": loaded["names"].get(name)}


def format_result(result):
    if result["records"] is None:
        return f"No local MNS record for {result['name']} (registry scope: {result['scope']})."
    rows = [f"{result['name']}  [local static registry]"]
    rows.extend(f"  {record['type']:<9} {record['value']} (TTL {record['ttl']}s)"
                for record in result["records"])
    rows.append("Local development alias only; this name is not resolved by public DNS or Mythchain state.")
    return "\n".join(rows)
