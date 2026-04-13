# Activity Registration and Funding Audit Management Platform

## Start (Docker)
Prepare required environment variables first (PowerShell example):
```powershell
$env:APP_ENV="dev"
$env:DATABASE_URL="<set-postgres-sqlalchemy-dsn>"
$env:SECRET_KEY="<generate-a-long-random-secret>"
$env:ADMIN_BOOTSTRAP_PASSWORD="<set-strong-admin-password>"
$env:DEV_SEED_DEMO_USERS="true"
$env:REVIEWER_BOOTSTRAP_PASSWORD="<set-reviewer-password>"
$env:FINANCE_BOOTSTRAP_PASSWORD="<set-finance-password>"
$env:APPLICANT_BOOTSTRAP_PASSWORD="<set-applicant-password>"
```

You can copy from `.env.example` and then fill your local values.

```bash
docker compose up --build -d
```

## Services
- Frontend: `http://localhost:3001`
- Backend: `http://localhost:8001`
- Backend OpenAPI: `http://localhost:8001/docs`
- PostgreSQL: `localhost:5432`

## Credentials
- `admin` is always bootstrapped using `ADMIN_BOOTSTRAP_PASSWORD`.
- `reviewer`, `finance`, and `applicant` are bootstrapped only when `DEV_SEED_DEMO_USERS=true`, using their corresponding `*_BOOTSTRAP_PASSWORD` values.

## Quick verification
1. Login on frontend.
2. Create registration.
3. Upload checklist material (default checklist: `proposal`, `id_document`, `budget_plan`).
4. Set funding budget before creating transactions.
5. Load report summary.
6. Create transaction.

## Backend tests (recommended, no frontend required)
Run from project root:

```bash
docker compose run --rm -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/backend -e BASE_URL=http://backend:8000/api -e ROOT_URL=http://backend:8000 -e ADMIN_TEST_PASSWORD="${ADMIN_BOOTSTRAP_PASSWORD}" -e REVIEWER_TEST_PASSWORD="${REVIEWER_BOOTSTRAP_PASSWORD}" -e FINANCE_TEST_PASSWORD="${FINANCE_BOOTSTRAP_PASSWORD}" -e APPLICANT_TEST_PASSWORD="${APPLICANT_BOOTSTRAP_PASSWORD}" backend python -m pytest -q unit_tests API_tests
```

Run a single file:

```bash
docker compose run --rm -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/backend backend python -m pytest -q unit_tests/test_rules.py
docker compose run --rm -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/backend -e ADMIN_TEST_PASSWORD="${ADMIN_BOOTSTRAP_PASSWORD}" -e REVIEWER_TEST_PASSWORD="${REVIEWER_BOOTSTRAP_PASSWORD}" -e FINANCE_TEST_PASSWORD="${FINANCE_BOOTSTRAP_PASSWORD}" -e APPLICANT_TEST_PASSWORD="${APPLICANT_BOOTSTRAP_PASSWORD}" backend python -m pytest -q API_tests/test_api.py
```

Run a single test:

```bash
docker compose run --rm -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/backend backend python -m pytest -q API_tests/test_api.py::test_health_endpoint
```

## Common troubleshooting
- If you see `file or directory not found` for `/app/unit_tests` or `/app/API_tests`, use the `docker compose run ... -v "${PWD}:/workspace"` commands above.
- If PostgreSQL auth fails in pgAdmin after changing env credentials, rebuild with fresh volume:
  ```bash
  docker compose down -v
  docker compose up --build -d
  ```
- If upload says `Registration not found`, create a registration first and use that returned registration ID.

## Optional stop command
```bash
docker compose down
```

## Submission checklist (manual-aligned)
- Required structure present:
  - `backend/`, `frontend/`
  - `../self-doc/prompt.md`
  - `../self-doc/trajectory.json` (must be converted from session trace before final submission)
  - `../docs/questions.md`
  - `../docs/design.md`
  - `../docs/api-spec.md`
  - `unit_tests/`, `API_tests/`, `run_tests.sh`
- Run docker cold start:
  - `docker compose down -v`
  - `docker compose up --build -d`
- Run tests:
  - `docker compose run --rm -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/backend -e BASE_URL=http://backend:8000/api -e ROOT_URL=http://backend:8000 backend python -m pytest -q unit_tests API_tests`
- Capture screenshots of running app and include with submission.
- Complete and attach self-test report (`../self-doc/self-test-report.md`).

## Notes
- `../self-doc/trajectory.json` currently requires conversion from the raw session trace via your provided `convert_ai_session.py` process.
- Do not include dependency folders (`node_modules`, `.venv`, build caches) in the submission package.
