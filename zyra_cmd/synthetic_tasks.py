"""Deterministic, local-only preview of bounded synthetic ZYRA tasks.

This first scheduler increment only previews task specifications. It never
registers with Mythchain, broadcasts through P2P, invokes a Miner, or creates a
reward. Live scheduling requires an on-chain synthetic origin and emission budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass

from ai.execution.contract import RUNTIME, contract_hash, validate_contract

CATALOG_VERSION = "synthetic-catalog-v1"
MAX_PREVIEW_COUNT = 8


@dataclass(frozen=True)
class SyntheticTaskTemplate:
    template_id: str
    category: str
    difficulty: str
    prompt: str
    profile: str
    checks: tuple[dict, ...]


_CATALOG = (
    SyntheticTaskTemplate(
        template_id="cli-arithmetic-001",
        category="python-cli",
        difficulty="easy",
        prompt=(
            "Create a small Python CLI at main.py that calculates 6 * 7 and prints 42. "
            "Use only the Python standard library. Include test_suite.py, requirements.txt, "
            "README.md, and zyra.json; do not include sample user data."
        ),
        profile="python",
        checks=(
            {"id": "application-runs", "description": "The CLI exits successfully", "weight": 40,
             "hard_gate": True, "check": {"type": "application_runs"}},
            {"id": "expected-output", "description": "The CLI prints 42", "weight": 60,
             "hard_gate": True, "check": {"type": "stdout_contains", "text": "42"}},
        ),
    ),
    SyntheticTaskTemplate(
        template_id="json-compact-output-001",
        category="json",
        difficulty="easy",
        prompt=(
            "Create a Python CLI at main.py that uses the standard-library json module "
            "to print the compact JSON string {\"ok\":true,\"items\":[1,2,3]}. "
            "Include test_suite.py, requirements.txt, README.md, and zyra.json."
        ),
        profile="python",
        checks=(
            {"id": "application-runs", "description": "The JSON CLI exits successfully", "weight": 40,
             "hard_gate": True, "check": {"type": "application_runs"}},
            {"id": "compact-json", "description": "The expected JSON is printed", "weight": 60,
             "hard_gate": True,
             "check": {"type": "stdout_contains", "text": '{"ok":true,"items":[1,2,3]}'}},
        ),
    ),
    SyntheticTaskTemplate(
        template_id="text-normalizer-001",
        category="text-processing",
        difficulty="easy",
        prompt=(
            "Create a Python CLI at main.py that normalizes the fixed text '  ZYRA   TASK  ' "
            "by trimming and collapsing whitespace, then prints it in lowercase as "
            "'zyra task'. Use only the standard library and include the required tests, "
            "requirements.txt, README.md, and zyra.json."
        ),
        profile="python",
        checks=(
            {"id": "application-runs", "description": "The normalizer exits successfully", "weight": 40,
             "hard_gate": True, "check": {"type": "application_runs"}},
            {"id": "normalized-text", "description": "The normalized text is printed", "weight": 60,
             "hard_gate": True, "check": {"type": "stdout_contains", "text": "zyra task"}},
        ),
    ),
    SyntheticTaskTemplate(
        template_id="flask-health-001",
        category="flask-web",
        difficulty="medium",
        prompt=(
            "Create a small Flask health dashboard. The home page must show 'ZYRA test service'. "
            "Expose GET /health returning JSON {\"status\":\"ok\"}. Use only the base Flask "
            "runtime; include test_suite.py, requirements.txt, README.md, and zyra.json."
        ),
        profile="flask-web",
        checks=(
            {"id": "application-runs", "description": "The Flask app starts", "weight": 25,
             "hard_gate": True, "check": {"type": "application_runs"}},
            {"id": "home-page", "description": "The health dashboard is visible", "weight": 35,
             "hard_gate": True, "check": {"type": "browser_contains", "text": "ZYRA test service"}},
            {"id": "health-api", "description": "The health endpoint returns success", "weight": 40,
             "hard_gate": True,
             "check": {"type": "http", "path": "/health", "status": 200,
                       "content_type": "application/json", "json_equals": {"status": "ok"}}},
        ),
    ),
)


def catalog():
    """Return a copy-safe summary of the finite, reviewed task catalog."""
    return [
        {"template_id": item.template_id, "category": item.category, "difficulty": item.difficulty,
         "profile": item.profile}
        for item in _CATALOG
    ]


def _acceptance_for(template):
    if template.profile == "python":
        contract = {"version": 1, "runtime": RUNTIME, "profile": "python",
                    "entrypoint": "main.py", "args": [], "http_checks": []}
    else:
        contract = {
            "version": 1, "runtime": RUNTIME, "profile": "flask-web",
            "entrypoint": "app.py", "args": [], "port": 8000,
            "http_checks": [
                {"path": "/", "status": 200, "content_type": "text/html",
                 "contains": ["<html"]},
                {"path": "/health", "status": 200, "content_type": "application/json",
                 "json_equals": {"status": "ok"}},
            ],
            "browser_contains": ["ZYRA test service"],
        }
    contract["criteria"] = [dict(check, check=dict(check["check"])) for check in template.checks]
    return validate_contract(contract)


def generate_synthetic_tasks(*, seed: int, count: int = 1, category: str | None = None):
    """Generate reproducible preview tasks without publishing or rewarding them."""
    if not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not 1 <= count <= MAX_PREVIEW_COUNT:
        raise ValueError(f"count must be between 1 and {MAX_PREVIEW_COUNT}")
    templates = [template for template in _CATALOG if category is None or template.category == category]
    if not templates:
        raise ValueError(f"Unknown synthetic task category: {category}")
    if count > len(templates):
        raise ValueError(f"count exceeds the {len(templates)} reviewed template(s) in this selection")

    selected = []
    available = sorted(templates, key=lambda template: template.template_id)
    counter = 0
    while len(selected) < count:
        entropy = hashlib.sha256(f"{CATALOG_VERSION}:{seed}:{counter}".encode("utf-8")).digest()
        index = int.from_bytes(entropy[:8], "big") % len(available)
        selected.append(available.pop(index))
        counter += 1
    tasks = []
    for index, template in enumerate(selected):
        acceptance = _acceptance_for(template)
        task_key = f"{CATALOG_VERSION}:{seed}:{index}:{template.template_id}"
        preview_id = hashlib.sha256(task_key.encode("utf-8")).hexdigest()[:24]
        tasks.append({
            "preview_id": f"synthetic-preview-{preview_id}",
            "catalog_version": CATALOG_VERSION,
            "origin": "synthetic",
            "status": "preview_only_not_submitted",
            "reward_mode": "none",
            "seed": seed,
            "category": template.category,
            "difficulty": template.difficulty,
            "runtime_profile": template.profile,
            "prompt": template.prompt,
            "acceptance": acceptance,
            "acceptance_hash": contract_hash(acceptance),
        })
    return tasks


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preview deterministic synthetic ZYRA tasks; this command never submits or rewards them."
    )
    parser.add_argument("--seed", type=int, default=0, help="Reproducible selection seed (default: 0)")
    parser.add_argument("--count", type=int, default=1, help=f"Task count (1..{MAX_PREVIEW_COUNT})")
    parser.add_argument("--category", help="Limit selection to a reviewed category")
    parser.add_argument("--list", action="store_true", help="List available task templates")
    args = parser.parse_args(argv)
    result = catalog() if args.list else generate_synthetic_tasks(
        seed=args.seed, count=args.count, category=args.category
    )
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
