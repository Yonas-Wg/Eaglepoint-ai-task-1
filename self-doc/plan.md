# plan.md

## 1. Project Understanding

This is a full-stack system with:
- Frontend: Vue.js (form wizard + dashboards)
- Backend: FastAPI (REST APIs)
- Database: PostgreSQL
- Deployment: Docker (offline-first)

Core domains:
- Registration & materials
- Review workflow
- Financial management
- Security & auditing

---

## 2. High-Level Architecture

### Layers
- Frontend (Vue.js)
- Backend API (FastAPI)
- Database (PostgreSQL)
- File Storage (local disk)

### Backend structure
- API layer (routes)
- Service layer (business logic)
- Repository layer (DB access)
- Models (ORM schemas)

---

## 3. Core Modules Breakdown

### 3.1 Authentication & Security
- Login (username/password)
- Password hashing (bcrypt or similar)
- Failed attempts tracking (lock for 30 minutes after >=10 attempts / 5 min)
- Role-based access (Applicant, Reviewer, Admin, Finance)
- Role-based masking for sensitive fields (ID number, contact details)
- Access auditing and permission isolation
- Encryption for sensitive configurations

---

### 3.2 Registration Module
- Create registration (form wizard)
- Save draft / submit
- Validate fields (required, types)
- Deadline enforcement (lock after deadline)

---

### 3.3 Material Management
- Upload files (PDF/JPG/PNG)
- Validate:
  - Single file ≤20MB
  - Total ≤200MB
- Version control (max 3 versions)
- Status labels:
  - Pending
  - Submitted
  - Needs Correction

---

### 3.4 Supplementary Submission
- Allow within 72 hours
- Restrict to "Needs Correction"
- Record correction reason

---

### 3.5 Review Workflow
- State machine:
  - Submitted → Supplemented → Approved / Rejected / Canceled / Waitlist
- Batch review (≤50)
- Add comments
- Store logs (audit trail)

---

### 3.6 Financial Module
- Record income/expenses
- Upload invoices
- Budget tracking
- Overspending rule:
  - >10% → warning + confirmation

---

### 3.7 Quality Metrics
- Approval rate
- Correction rate
- Overspending rate
- Trigger alerts when thresholds exceeded

---

### 3.8 File Storage
- Store files locally
- Generate SHA-256 hash
- Detect duplicates (per activity)
- Reserve similarity/duplicate check endpoint (disabled by feature flag by default)

---

### 3.9 Reports
- Export:
  - Audit
  - Compliance
  - Reconciliation
- Format: CSV / PDF
- Whitelist policy export for data collection scope

---

### 3.10 Backup & Recovery
- Daily DB backup
- File backup
- One-click restore

---

## 4. Database Design (Initial Tables)

- users
- roles
- registrations
- materials
- material_versions
- reviews
- workflows
- transactions
- funding_accounts
- audit_logs
- metrics
- data_collection_batches
- whitelist_policies

---

## 5. API Design (Examples)

### Auth
- POST /auth/login

### Registration
- POST /registrations
- GET /registrations/:id

### Materials
- POST /materials/upload
- GET /materials/:id

### Review
- POST /reviews/batch
- PATCH /reviews/:id/status

### Finance
- POST /transactions
- GET /reports

### System / Policy
- GET /similarity-check (disabled by default)
- GET /whitelist-policies/export

---

## 6. Frontend Plan (Vue.js)

Pages:
- Login
- Dashboard
- Registration Wizard
- Materials Upload
- Review List
- Financial Dashboard
- Reports

Components:
- Form Wizard
- File Upload
- Status Badge
- Table (batch actions)
- Modal (warnings)

---

## 7. Docker Plan

Services:
- frontend (Vue)
- backend (FastAPI)
- db (PostgreSQL)

Requirements:
- docker-compose.yml
- Expose ports:
  - frontend: 3000
  - backend: 8000
  - db: 5432

---

## 8. Testing Plan

### unit_tests/
- business logic
- validation rules
- workflow transitions

### API_tests/
- auth
- registration
- review
- finance
- permissions and masking

### run_tests.sh
- run all tests
- print pass/fail
- include normal inputs, missing params, and permission error cases

---

## 9. Logging & Error Handling

- Standard API error format:
  { "code": 400, "msg": "error message" }

- Log:
  - login attempts
  - transactions
  - review actions

---

## 10. Final Deliverables Checklist

- Full project structure
- Docker working (docker compose up)
- README.md
- prompt.md
- metadata.json
- trajectory.json
- questions.md
- docs/design.md
- docs/api-spec.md
- tests (unit + API)
- run_tests.sh
- screenshots
- self-test report

---

## 11. Execution Order (IMPORTANT)

1. Analyze prompt + write metadata.json ✅
2. Write questions.md ✅
3. Design DB schema
4. Build backend (FastAPI)
5. Build frontend (Vue)
6. Add validation + workflow
7. Add Docker setup
8. Write tests
9. Write docs
10. Self-test (clean environment)
11. Submit