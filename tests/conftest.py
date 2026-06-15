"""
conftest.py — captures each test's outcome, docstring and duration into
reporting/results.json so reporting/render_report.py can produce a NOC-styled
report. No external plugin needed (avoids pytest-html / pytest-json-report deps).
"""
import json
import os
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "reporting", "results.json")
_results = []
_start = time.time()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call":
        return
    doc = (item.function.__doc__ or "").strip()
    _results.append({
        "name": item.name,
        "nodeid": item.nodeid,
        "outcome": rep.outcome,           # passed | failed | skipped
        "summary": doc.split("\n")[0] if doc else "",
        "duration_ms": round(rep.duration * 1000, 2),
        "longrepr": str(rep.longrepr) if rep.failed else "",
    })


def pytest_sessionfinish(session, exitstatus):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    passed = sum(1 for r in _results if r["outcome"] == "passed")
    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_ms": round((time.time() - _start) * 1000, 2),
        "total": len(_results),
        "passed": passed,
        "failed": sum(1 for r in _results if r["outcome"] == "failed"),
        "skipped": sum(1 for r in _results if r["outcome"] == "skipped"),
        "exit_status": int(exitstatus),
        "results": _results,
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)
