# questions.md

## 1. Material Version Handling

- Question: The prompt states that up to three versions of the same material can be retained, but does not specify what happens when a fourth version is uploaded.
- Assumption: The system should automatically discard or archive the oldest version when a new version exceeds the limit of three.
- Solution: Implemented a version control mechanism where the oldest version is soft-deleted when a fourth upload occurs, ensuring only the latest three versions are retained.

---

## 2. Supplementary Submission Scope

- Question: It is unclear whether supplementary submissions allow modification of all materials or only those marked as "Needs Correction".
- Assumption: Only materials marked as "Needs Correction" can be modified during the supplementary submission window.
- Solution: Implemented supplementary upload restrictions so only materials flagged as "Needs Correction" can be modified during the supplementary window, enforced at the API level.

---

## 3. Deadline Lock Behavior

- Question: The prompt states materials are locked after the deadline, but does not clarify if reviewers or admins can override this lock.
- Assumption: Only system administrators can override the lock for exceptional cases.
- Solution: Implemented role-based deadline control with protected deadline management endpoints reserved for administrators.

---

## 4. Batch Review Partial Failure

- Question: During batch review (≤50 entries), what happens if some entries fail validation while others succeed?
- Assumption: The system should process valid entries and return errors for failed ones without rolling back the entire batch.
- Solution: Implemented partial success handling with per-item status reporting in batch review operations.

---

## 5. Overspending Alert Enforcement

- Question: The prompt specifies a frontend warning when expenses exceed 10% of the budget, but does not clarify whether backend enforcement is required.
- Assumption: Backend validation must also enforce this rule to prevent bypassing frontend checks.
- Solution: Implemented backend validation to block overspending transactions unless secondary confirmation is explicitly provided.

---

## 6. Duplicate File Detection Scope

- Question: The prompt mentions SHA-256 fingerprinting but does not specify whether duplicate detection is per user, per activity, or global.
- Assumption: Duplicate detection should be scoped per activity to avoid cross-project conflicts.
- Solution: Implemented SHA-256 hashing with duplicate checks scoped to the same activity context.

---

## 7. Review Workflow Transitions

- Question: The allowed transitions between states (e.g., Submitted → Approved) are not explicitly defined.
- Assumption: The workflow must follow strict transitions: Submitted → Supplemented → Approved/Rejected → (optional) Waitlist Promotion or Cancellation.
- Solution: Implemented a state machine that enforces valid workflow transitions and rejects invalid status changes at the API level.

---

## 8. File Storage Structure

- Question: The prompt specifies local file storage but does not define directory structure or naming conventions.
- Assumption: Files should be organized by activity ID and material type with unique hashed filenames.
- Solution: Implemented a structured local storage system: /storage/{activity_id}/{material_type}/{file_hash_filename}.

---

## 9. Authentication Session Management

- Question: The prompt defines login security but does not specify session handling (JWT vs server session).
- Assumption: JWT-based stateless authentication is suitable for offline deployment.
- Solution: Implemented JWT authentication with expiration for protected API access.

---

## 10. Access Lock Timing Precision

- Question: The lock rule specifies ≥10 failed attempts within 5 minutes, but does not clarify if attempts reset after success.
- Assumption: Failed attempt counters reset after a successful login.
- Solution: Implemented a rolling failed-attempt window with reset on successful authentication.

---

## 11. Quality Metrics Calculation Frequency

- Question: It is unclear whether metrics (approval rate, correction rate, overspending rate) are computed in real-time or batch.
- Assumption: Metrics should be updated in near real-time after relevant actions.
- Solution: Implemented quality metric generation on report summary and key workflow/financial updates.

---

## 12. Backup and Recovery Scope

- Question: The prompt mentions daily backups but does not define whether files are included or only database records.
- Assumption: Both database and file storage must be included in backups.
- Solution: Implemented local backup and one-click recovery endpoints for storage snapshots in offline mode.

---

## 13. Similarity Check Feature Behavior

- Question: The prompt states the similarity/duplicate check interface is reserved but disabled—should it be accessible?
- Assumption: The interface exists but is hidden or disabled by default.
- Solution: Implemented the similarity-check endpoint gated behind a disabled-by-default feature flag.

---

## 14. Role-Based Data Masking Rules

- Question: The prompt mentions masking sensitive data but does not define masking levels per role.
- Assumption: Applicants see full data, reviewers see partial masking, admins see full access.
- Solution: Implemented role-based masking behavior for sensitive fields in registration retrieval APIs.

---

## 15. Report Export Format

- Question: The format for exported reports (audit, compliance, reconciliation) is not specified.
- Assumption: CSV and PDF formats are sufficient for offline usage.
- Solution: Implemented report export endpoints supporting CSV and PDF output modes.