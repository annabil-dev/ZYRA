"""Reviewed synthetic task catalog and local-only preview tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass

from ai.execution.contract import RUNTIME, contract_hash, validate_contract

CATALOG_VERSION = "synthetic-catalog-v2"
MAX_CATALOG_TASKS = 24
REWARD_CATEGORY_ORDER = ("light", "medium", "heavy", "very_heavy")
REWARD_DIFFICULTY = {
    "light": "easy",
    "medium": "medium",
    "heavy": "hard",
    "very_heavy": "very_hard",
}


@dataclass(frozen=True)
class SyntheticTaskTemplate:
    template_id: str
    category: str
    difficulty: str
    prompt: str
    profile: str
    checks: tuple[dict, ...]

    @property
    def reward_category(self) -> str:
        return {value: key for key, value in REWARD_DIFFICULTY.items()}[self.difficulty]


def _python_task(template_id: str, category: str, difficulty: str,
                 requirement: str, expected: str) -> SyntheticTaskTemplate:
    prompt = (
        f"[Synthetic simulation task {template_id}] Create a Python CLI in main.py that {requirement} "
        f"and prints exactly this required result: {expected!r}. Use only the Python standard library. "
        "Include test_suite.py with unittest tests, an empty requirements.txt, README.md with the "
        "required sections, and zyra.json with the runtime manifest. Do not use network access or real data."
    )
    return SyntheticTaskTemplate(
        template_id=template_id,
        category=category,
        difficulty=difficulty,
        prompt=prompt,
        profile="python",
        checks=(
            {"id": "application-runs", "description": "The CLI exits successfully", "weight": 40,
             "hard_gate": True, "check": {"type": "application_runs"}},
            {"id": "expected-output", "description": "The CLI prints its expected result", "weight": 60,
             "hard_gate": True, "check": {"type": "stdout_contains", "text": expected}},
        ),
    )


def _flask_task(template_id: str, category: str, difficulty: str, requirement: str,
                page_text: str, route: str, response: dict) -> SyntheticTaskTemplate:
    prompt = (
        f"[Synthetic simulation task {template_id}] Create a local-only Flask application in app.py that "
        f"implements this feature: {requirement} The home page must visibly include {page_text!r}. "
        "GET /health must return JSON {\"status\":\"ok\"}. Add the specified local API route. "
        "Include test_suite.py, requirements.txt pinned to Flask==3.1.3, README.md with the required "
        "sections, and zyra.json with the runtime manifest. No external APIs, network access, or real data."
    )
    return SyntheticTaskTemplate(
        template_id=template_id,
        category=category,
        difficulty=difficulty,
        prompt=prompt,
        profile="flask-web",
        checks=(
            {"id": "application-runs", "description": "The Flask application starts", "weight": 20,
             "hard_gate": True, "check": {"type": "application_runs"}},
            {"id": "home-page", "description": "The requested page is visible", "weight": 35,
             "hard_gate": True, "check": {"type": "browser_contains", "text": page_text}},
            {"id": "local-api", "description": "The local API returns its expected JSON", "weight": 45,
             "hard_gate": True,
             "check": {"type": "http", "path": route, "status": 200,
                       "content_type": "application/json", "json_equals": response}},
        ),
    )


_CATALOG = (
    # Light — six small standard-library tasks.
    _python_task("cli-arithmetic-001", "python-cli", "easy", "calculates 6 * 7", "42"),
    _python_task("json-compact-001", "json", "easy", "prints compact JSON for a healthy service",
                 '{"ok":true,"items":[1,2,3]}'),
    _python_task("text-normalizer-001", "text-processing", "easy", "trims and collapses whitespace",
                 "zyra task"),
    _python_task("csv-row-count-001", "csv", "easy", "counts three fixed data rows", "rows=3"),
    _python_task("list-deduplicator-001", "collections", "easy", "removes duplicates while preserving order",
                 "alpha,beta,gamma"),
    _python_task("slug-generator-001", "text-processing", "easy", "makes a lowercase hyphenated slug",
                 "zyra-test-task"),

    # Medium — six data-processing and small web-service tasks.
    _python_task("csv-average-001", "csv", "medium", "calculates the mean of fixed values 10, 20, and 30",
                 "average=20"),
    _python_task("word-frequency-001", "text-processing", "medium", "counts repeated words in fixed text",
                 "zyra=2"),
    _python_task("json-config-summary-001", "json", "medium", "summarizes a fixed JSON configuration",
                 "workers=3,mode=test"),
    _python_task("log-severity-001", "log-analysis", "medium", "counts fixed INFO and WARN log records",
                 "INFO=2,WARN=1"),
    _flask_task("flask-health-001", "flask-web", "medium", "a tiny health dashboard",
                "ZYRA test service", "/api/status", {"service": "zyra-test", "status": "ok"}),
    _flask_task("flask-reading-list-001", "flask-web", "medium", "a read-only reading list",
                "Reading List", "/api/books", {"books": ["Task Systems", "Local Testing"]}),

    # Heavy — six multi-view local Flask applications.
    _flask_task("flask-inventory-001", "inventory", "hard", "an inventory summary dashboard",
                "Inventory Overview", "/api/inventory", {"items": 3, "low_stock": 1}),
    _flask_task("flask-expense-summary-001", "finance-demo", "hard", "a fixed demo expense report",
                "Expense Summary", "/api/summary", {"currency": "TEST", "total": 125}),
    _flask_task("flask-support-queue-001", "support-tools", "hard", "a support-ticket queue",
                "Support Queue", "/api/tickets", {"open": 2, "closed": 1}),
    _flask_task("flask-deploy-status-001", "devops-demo", "hard", "a local deployment status board",
                "Deployment Status", "/api/deployments", {"failed": 0, "healthy": 2}),
    _flask_task("flask-book-catalog-001", "catalog", "hard", "a searchable demo book catalog",
                "Book Catalog", "/api/catalog", {"count": 3, "category": "testing"}),
    _flask_task("flask-task-board-001", "task-management", "hard", "a task board with status totals",
                "Task Board", "/api/tasks/summary", {"done": 2, "todo": 1}),

    # Very heavy — six local multi-route dashboards with joined deterministic data.
    _flask_task("flask-kanban-flow-001", "project-management", "very_hard",
                "a three-column Kanban board with fixed cards and column counts",
                "Kanban Workspace", "/api/board", {"columns": 3, "cards": 5, "done": 1}),
    _flask_task("flask-incident-center-001", "operations", "very_hard",
                "an incident center with severity totals and a recent-incident list",
                "Incident Center", "/api/incidents/summary", {"critical": 1, "open": 2}),
    _flask_task("flask-release-tracker-001", "devops-demo", "very_hard",
                "a release tracker showing version, checks, and rollout state",
                "Release Tracker", "/api/release", {"version": "1.2.0-test", "checks_passed": 4,
                                                        "rollout": "ready"}),
    _flask_task("flask-gradebook-001", "education-demo", "very_hard",
                "a local gradebook with class statistics and student count",
                "Class Gradebook", "/api/grades/summary", {"students": 4, "average": 82}),
    _flask_task("flask-usage-dashboard-001", "analytics-demo", "very_hard",
                "an API usage dashboard with deterministic daily totals",
                "Usage Analytics", "/api/usage", {"requests": 120, "errors": 3, "window": "today"}),
    _flask_task("flask-order-tracker-001", "commerce-demo", "very_hard",
                "an order tracker with status totals and a recent order table",
                "Order Tracker", "/api/orders/summary", {"orders": 5, "pending": 2, "shipped": 3}),
)


def catalog():
    """Return a copy-safe summary of all 24 reviewed task templates."""
    return [
        {"template_id": item.template_id, "category": item.category,
         "difficulty": item.difficulty, "reward_category": item.reward_category,
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
                {"path": "/", "status": 200, "content_type": "text/html", "contains": ["<html"]},
                {"path": "/health", "status": 200, "content_type": "application/json",
                 "json_equals": {"status": "ok"}},
            ],
            "browser_contains": [template.checks[1]["check"]["text"]],
        }
    contract["criteria"] = [dict(check, check=dict(check["check"])) for check in template.checks]
    return validate_contract(contract)


def _task_spec(template, seed, sequence):
    acceptance = _acceptance_for(template)
    task_key = f"{CATALOG_VERSION}:{seed}:{sequence}:{template.template_id}"
    synthetic_id = hashlib.sha256(task_key.encode("utf-8")).hexdigest()[:24]
    return {
        "preview_id": f"synthetic-preview-{synthetic_id}",
        "catalog_version": CATALOG_VERSION,
        "origin": "synthetic",
        "status": "preview_only_not_submitted",
        "reward_mode": "chain-task-category",
        "seed": seed,
        "template_id": template.template_id,
        "category": template.category,
        "difficulty": template.difficulty,
        "reward_category": template.reward_category,
        "runtime_profile": template.profile,
        "prompt": template.prompt,
        "acceptance": acceptance,
        "acceptance_hash": contract_hash(acceptance),
    }


def _matching_templates(category):
    return [template for template in _CATALOG
            if category is None or category in (template.category, template.reward_category)]


def generate_synthetic_tasks(*, seed: int, count: int = 1, category: str | None = None):
    """Return a deterministic preview only; this function never submits or rewards."""
    if not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not 1 <= count <= MAX_CATALOG_TASKS:
        raise ValueError(f"count must be between 1 and {MAX_CATALOG_TASKS}")
    templates = _matching_templates(category)
    if not templates:
        raise ValueError(f"Unknown synthetic task category: {category}")
    if count > len(templates):
        raise ValueError(f"count exceeds the {len(templates)} reviewed template(s) in this selection")

    rng = random.Random(seed)
    templates = sorted(templates, key=lambda template: template.template_id)
    rng.shuffle(templates)
    return [_task_spec(template, seed, index) for index, template in enumerate(templates[:count])]


def randomized_task_specs(*, seed: int | None = None, count: int = MAX_CATALOG_TASKS):
    """Yield a random mix; each four-task block covers all four reward categories."""
    if not 1 <= count <= MAX_CATALOG_TASKS:
        raise ValueError(f"count must be between 1 and {MAX_CATALOG_TASKS}")
    rng = random.Random(seed)
    by_category = {category: [item for item in _CATALOG if item.reward_category == category]
                   for category in REWARD_CATEGORY_ORDER}
    for items in by_category.values():
        items.sort(key=lambda item: item.template_id)
    yielded = 0
    while yielded < count:
        categories = list(REWARD_CATEGORY_ORDER)
        rng.shuffle(categories)
        for category in categories:
            pool = by_category[category]
            if not pool:
                pool.extend(item for item in _CATALOG if item.reward_category == category)
                pool.sort(key=lambda item: item.template_id)
                rng.shuffle(pool)
            template = pool.pop(rng.randrange(len(pool)))
            yield _task_spec(template, seed if seed is not None else 0, yielded)
            yielded += 1
            if yielded >= count:
                break

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preview deterministic synthetic task specs; no chain/P2P submission is done here."
    )
    parser.add_argument("--seed", type=int, default=0, help="Reproducible selection seed (default: 0)")
    parser.add_argument("--count", type=int, default=1, help=f"Preview count (1..{MAX_CATALOG_TASKS})")
    parser.add_argument("--category", help="Filter by domain category or reward category")
    parser.add_argument("--list", action="store_true", help="List all reviewed task templates")
    args = parser.parse_args(argv)
    result = catalog() if args.list else generate_synthetic_tasks(
        seed=args.seed, count=args.count, category=args.category
    )
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
