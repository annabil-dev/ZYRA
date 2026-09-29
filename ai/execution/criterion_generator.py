"""Generate a bounded, executable acceptance rubric from a Client task prompt."""

import json
import re

from .scoring import validate_criteria


def _fallback_criteria(prompt, profile):
    criteria = [{
        "id": "application-runs",
        "description": "The delivered application starts and exits successfully.",
        "weight": 50 if profile == "python" else 40,
        "hard_gate": True,
        "check": {"type": "application_runs"},
    }]
    if profile == "flask-web":
        criteria.append({
            "id": "home-http",
            "description": "The web application's home page is available.",
            "weight": 60,
            "hard_gate": True,
            "check": {"type": "http", "path": "/", "status": 200},
        })
        quoted_texts = re.findall(
            r"\b(?:show|shows|display|displays|contain|contains)\b[^\n\"']{0,60}[\"']([^\"']{1,120})[\"']",
            prompt, re.IGNORECASE,
        )
        for index, text in enumerate(dict.fromkeys(quoted_texts)):
            criteria.append({
                "id": f"visible-text-{index + 1}",
                "description": f"The browser displays {text!r} as requested.",
                "weight": 20,
                "hard_gate": False,
                "check": {"type": "browser_contains", "text": text},
            })
        endpoint_paths = re.findall(r"(?<![\w:])/(?:api/)?[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*", prompt)
        for index, path in enumerate(dict.fromkeys(endpoint_paths)):
            criteria.append({
                "id": f"endpoint-{index + 1}",
                "description": f"The requested endpoint {path} responds successfully.",
                "weight": 20,
                "hard_gate": False,
                "check": {"type": "http", "path": path, "status": 200},
            })
    else:
        expected_texts = re.findall(
            r"\b(?:print|prints|output|outputs|display|displays|return|returns)\b"
            r"[^\n\"']{0,60}[\"']([^\"']{1,120})[\"']",
            prompt, re.IGNORECASE,
        )
        unique = list(dict.fromkeys(expected_texts))[:5]
        for index, text in enumerate(unique):
            criteria.append({
                "id": f"expected-output-{index + 1}",
                "description": f"The program outputs {text!r} as requested.",
                "weight": 50,
                "hard_gate": False,
                "check": {"type": "stdout_contains", "text": text},
            })
        if not unique:
            criteria[0]["weight"] = 100
    return criteria


def _request_model_criteria(prompt, profile, generator):
    instruction = f"""Create a small objective acceptance rubric for this Client task.
Return ONLY JSON in the form {{"criteria":[...]}}. Do not include markdown or commentary.
Use only these executable check types:
- application_runs: {{"type":"application_runs"}}
- python stdout_contains: {{"type":"stdout_contains","text":"...","args":[],"stdin":"..."}}
- flask-web http: {{"type":"http","path":"/path","status":200,"content_type":"...","contains":[],"json_keys":[],"json_equals":{{}}}}
- flask-web browser_contains: {{"type":"browser_contains","text":"..."}}
- flask-web browser_fetch: {{"type":"browser_fetch","path":"/api/path"}}
Every item must contain id (unique lower-case kebab-case), description, positive integer weight,
hard_gate (boolean), and check. Include application_runs as a hard gate. Derive checks only from
the task's stated requirements; do not invent external services, dependencies, routes, or outputs.
Prefer 2-6 criteria. Weights express relative importance and need not sum to 100.
Selected profile: {profile}
Client task:
{prompt}
"""
    chunks = generator.generate(prompt=instruction, history=[], max_tokens=1400,
                                temperature=0.1, top_k=20, top_p=0.8, use_tools=False)
    text = ""
    for chunk in chunks:
        if isinstance(chunk, tuple) and chunk:
            text = chunk[0]
        elif isinstance(chunk, str):
            text = chunk
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("criteria generator did not return a JSON object")
    value = json.loads(match.group(0))
    if not isinstance(value, dict) or not isinstance(value.get("criteria"), list):
        raise ValueError("criteria generator JSON must contain a criteria list")
    criteria = validate_criteria(value["criteria"])
    from .contract import validate_criterion_check
    for criterion in criteria:
        if "check" not in criterion:
            raise ValueError(f"generated criterion {criterion['id']} has no executable check")
        validate_criterion_check(criterion["check"], profile)
    if not any(item["check"].get("type") == "application_runs" and item["hard_gate"]
               for item in criteria):
        raise ValueError("generated rubric must include application_runs as a hard gate")
    return criteria


def generate_criteria(prompt, profile, generator=None):
    """Use the local model when available; fall back to conservative runtime checks."""
    if generator is not None and callable(getattr(generator, "generate", None)):
        try:
            return _request_model_criteria(prompt, profile, generator), "local-model"
        except Exception:
            # Invalid, unavailable, or non-conforming model output cannot weaken the task.
            pass
    criteria = _fallback_criteria(prompt, profile)
    from .contract import validate_criterion_check
    for criterion in criteria:
        validate_criterion_check(criterion["check"], profile)
    return criteria, "runtime-fallback"
