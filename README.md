# Activity Registration and Funding Audit Management Platform

## Start (Docker)
```bash
docker compose up --build -d
```

## Services
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Backend OpenAPI: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`

## Test credentials
- Username: `admin`
- Password: `admin123`

## Quick verification
1. Login on frontend.
2. Create registration.
3. Load report summary.
4. Create transaction.

## Backend tests (recommended, no frontend required)
Run from project root:

```bash
docker compose run --rm -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/repo/backend -e BASE_URL=http://backend:8000/api -e ROOT_URL=http://backend:8000 backend python -m pytest -q unit_tests API_tests
```

Run a single file:

```bash
docker compose run --rm -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/repo/backend backend python -m pytest -q unit_tests/test_rules.py
docker compose run --rm -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/repo/backend backend python -m pytest -q API_tests/test_api.py
```

Run a single test:

```bash
docker compose run --rm -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/repo/backend backend python -m pytest -q API_tests/test_api.py::test_health_endpoint
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
  - `repo/` source project
  - `prompt.md`
  - `trajectory.json` (must be converted from session trace before final submission)
  - `docs/questions.md`
  - `docs/design.md`
  - `docs/api-spec.md`
  - `unit_tests/`, `API_tests/`, `run_tests.sh`
- Run docker cold start:
  - `docker compose down -v`
  - `docker compose up --build -d`
- Run tests:
  - `docker compose run --rm -v "${PWD}:/workspace" -w /workspace -e PYTHONPATH=/workspace/repo/backend -e BASE_URL=http://backend:8000/api -e ROOT_URL=http://backend:8000 backend python -m pytest -q unit_tests API_tests`
- Capture screenshots of running app and include with submission.
- Complete and attach self-test report (`docs/self-test-report.md`).

## Notes
- `trajectory.json` currently requires conversion from the raw session trace via your provided `convert_ai_session.py` process.
- Do not include dependency folders (`node_modules`, `.venv`, build caches) in the submission package.
