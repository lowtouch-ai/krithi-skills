"""Reusable pytest-playwright fixtures added by validate-pr (merge into tests/e2e/conftest.py). Commit with the tests.

- console_errors (autouse): collects browser console errors, page errors, failed requests and HTTP 5xx responses for
  every test that uses `page`; when VALIDATE_PR_CONSOLE_DIR is set they are written there as <test-name>.json.
- checkpoint(page, request, name): saves a full-page screenshot at an important validation point
  (into VALIDATE_PR_SCREENSHOT_DIR when validate-pr runs the tests).
- require_env("E2E_USER", "E2E_PASSWORD"): read credentials from the environment, skip with a reason if missing.
"""
import json
import os
import re
from pathlib import Path

import pytest


def _slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:60] or "test"


@pytest.fixture(autouse=True)
def console_errors(request):
    if "page" not in request.fixturenames:
        yield []
        return
    page = request.getfixturevalue("page")
    errors = []
    page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.method} {r.url} {r.failure or ''}"))
    page.on("response", lambda r: errors.append(f"http {r.status}: {r.request.method} {r.url}") if r.status >= 500 else None)
    yield errors
    out = os.environ.get("VALIDATE_PR_CONSOLE_DIR")
    if out and errors:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / f"{_slug(request.node.name)}.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")


def checkpoint(page, request, name):
    out = Path(os.environ.get("VALIDATE_PR_SCREENSHOT_DIR", "test-results/checkpoints"))
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / f"{_slug(request.node.name)}__{_slug(name)}.png"), full_page=True)


def require_env(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        pytest.skip(f"needs environment variables: {', '.join(missing)}")
    return {n: os.environ[n] for n in names}
