# Architecture Design

- Frontend (`repo/frontend`): Vue 3 + Vue Router UI for login, registration wizard, dashboard, and finance/review/system workflows.
- Backend (`repo/backend`): FastAPI REST APIs with validation, auth, workflow logic, reporting, and backup/recovery.
- Database (`postgres:14`): PostgreSQL for users, registrations, review records, transactions, and audit logs.
- Storage (`repo/storage`): local disk storage for uploaded materials and hash-based duplicate checks.

## Key decisions

- Username/password login only, with bcrypt password hashing and JWT token auth.
- Account lock policy: lock for 30 minutes after >=10 failures within 5 minutes.
- Role isolation via endpoint guards and role-based data masking on sensitive fields.
- Material rule set: file type/size constraints, max 3 versions, per-registration SHA-256 duplicate detection.
- Material lifecycle includes correction flags, supplementary submission window (72h), and deadline locking.
- Review state machine with controlled transitions and <=50 batch processing.
- Overspending guard: require secondary confirmation when expenses exceed 110% budget.
- Similarity-check endpoint is reserved and disabled by default.
- Added system-level data collection batch APIs, report export endpoints (CSV/PDF), and local backup/recovery endpoints (storage + DB snapshot file).
