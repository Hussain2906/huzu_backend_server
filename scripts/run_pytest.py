from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    os.environ.setdefault("PYTHONPATH", str(repo_root))
    os.makedirs("testing/reports/backend", exist_ok=True)

    args = ["-c", "testing/pytest.ini", "-ra", "testing/tests"]
    args.extend(sys.argv[1:])

    if has_module("pytest_html"):
        args.extend(["--html=testing/reports/backend/report.html", "--self-contained-html"])

    if has_module("pytest_jsonreport"):
        args.extend(["--json-report", "--json-report-file=testing/reports/backend/report.json"])

    if has_module("pytest_cov"):
        args.extend(["--cov=app", "--cov-report=term", "--cov-report=xml:testing/reports/backend/coverage.xml"])

    # JUnit XML is supported by pytest core
    args.append("--junitxml=testing/reports/backend/junit.xml")

    return pytest.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
