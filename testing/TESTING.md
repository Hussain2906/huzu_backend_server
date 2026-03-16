# Testing

This repo includes a full automated testing setup for backend APIs and frontend E2E flows.

## Prerequisites
- Python 3.11+ with `pip`
- Node.js 18+
- Frontend dependencies installed: `npm install` in `frontend/`
- Playwright browsers installed once: `npx playwright install`
- Backend dependencies installed: `pip install -r requirements.txt`

## One-command runs
From the repo root:
- `npm run test:all` — full backend + frontend suite (CI-friendly)
- `npm run test:backend` — backend unit/integration/contract tests only
- `npm run test:frontend` — frontend E2E only (headless by default)
- `npm run test:smoke` — fast smoke tests (backend + E2E tagged `@smoke`)
- `npm run test:full` — same as `test:all`
- `npm run test:report` — list available reports (optionally open HTML if `OPEN_REPORTS=1`)

## Reports & coverage
Backend reports are generated automatically by pytest:
- HTML: `testing/reports/backend/report.html`
- JUnit: `testing/reports/backend/junit.xml`
- JSON: `testing/reports/backend/report.json`
- Coverage: `testing/reports/backend/coverage.xml`

Note: HTML/JSON/Coverage reports require `pytest-html`, `pytest-json-report`, and `pytest-cov` to be installed.
If those plugins are missing, the test runner still succeeds and will only emit JUnit XML.

Frontend reports (Playwright):
- HTML: `testing/reports/frontend/playwright/index.html`
- JUnit: `testing/reports/frontend/junit.xml`
- JSON: `testing/reports/frontend/report.json`

## Headed/Debug mode
- Run headed E2E: `npm --prefix frontend run test:e2e:headed`
- Playwright debug: `PWDEBUG=1 npm --prefix frontend run test:e2e`

If you see `playwright: command not found`, make sure you installed frontend dependencies:
- `npm install --prefix frontend`
- `npx playwright install`

## Seed test data mode
For E2E and local test servers, a deterministic seed script is provided:
- `./.venv/bin/python scripts/seed_test_data.py`

The Playwright config automatically starts a fresh SQLite DB and seeds data using this script.
You can override the DB path or backend port:
- `E2E_DB_PATH=testing/.e2e/custom.db E2E_BACKEND_PORT=8010 npm --prefix frontend run test:e2e`

## CI usage
Minimum CI steps:
1. `pip install -r requirements.txt`
2. `npm install --prefix frontend`
3. `npx playwright install --with-deps`
4. `npm run test:full`

A convenience script is also available:
- `scripts/ci_test.sh` (see below)

## Updating snapshots/templates
No visual snapshots are tracked by default. If you add Playwright screenshots later, use:
- `npx playwright test --update-snapshots`

## Notes on edge cases
Some business rules (GSTIN/phone format validation, deletion constraints) are not enforced by the current backend. Tests document current behavior and highlight gaps. See failing/xfail notes in tests if you enable stricter validation later.
