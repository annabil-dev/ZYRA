"""Content-addressed identifiers for P2P artefacts."""

import hashlib
from pathlib import Path

CID_PREFIX = "sha256:"


def content_cid(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return CID_PREFIX + digest.hexdigest()


def is_sha256_cid(cid):
    if not isinstance(cid, str) or not cid.startswith(CID_PREFIX):
        return False
    value = cid[len(CID_PREFIX):]
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def verify_content_cid(path, cid):
    if not is_sha256_cid(cid):
        return None  # Legacy opaque CIDs are accepted without a content integrity claim.
    actual = content_cid(path)
    if actual != cid:
        raise ValueError(f"Artifact digest mismatch: expected {cid}, received {actual}")
    return actual
