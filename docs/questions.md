# questions.md

## 1. Material Version Handling

- Question: The prompt states that up to three versions of the same material can be retained, but does not specify what happens when a fourth version is uploaded.
- Assumption: The system should automatically discard or archive the oldest version when a new version exceeds the limit of three.
- Solution: Plan to implement a version control mechanism where the oldest version is soft-deleted when a fourth upload occurs, ensuring only the latest three versions are retained.

---

## 2. Supplementary Submission Scope

- Question: It is unclear whether supplementary submissions allow modification of all materials or only those marked as "Needs Correction".
- Assumption: Only materials marked as "Needs Correction" can be modified during the supplementary submission window.
- Solution: Plan to restrict supplementary uploads to only materials flagged as "Needs Correction" and enforce validation at the API level.

---

## 3. Deadline Lock Behavior

- Question: The prompt states materials are locked after the deadline, but does not clarify if reviewers or admins can override this lock.
- Assumption: Only system administrators can override the lock for exceptional cases.
- Solution: Plan to implement a role-based override where only admin users can unlock materials after the deadline via a protected endpoint.

---

## 4. Batch Review Partial Failure

- Question: During batch review (≤50 entries), what happens if some entries fail validation while others succeed?
- Assumption: The system should process valid entries and return errors for failed ones without rolling back the entire batch.
- Solution: Plan to implement partial success handling with per-item status reporting in batch operations.

---

## 5. Overspending Alert Enforcement

- Question: The prompt specifies a frontend warning when expenses exceed 10% of the budget, but does not clarify whether backend enforcement is required.
- Assumption: Backend validation must also enforce this rule to prevent bypassing frontend checks.
- Solution: Plan to add backend validation to block transactions exceeding the threshold unless a confirmation flag is explicitly provided.

---

## 6. Duplicate File Detection Scope

- Question: The prompt mentions SHA-256 fingerprinting but does not specify whether duplicate detection is per user, per activity, or global.
- Assumption: Duplicate detection should be scoped per activity to avoid cross-project conflicts.
- Solution: Plan to implement SHA-256 hashing with duplicate checks within the same activity context.

---

## 7. Review Workflow Transitions

- Question: The allowed transitions between states (e.g., Submitted → Approved) are not explicitly defined.
- Assumption: The workflow must follow strict transitions: Submitted → Supplemented → Approved/Rejected → (optional) Waitlist Promotion or Cancellation.
- Solution: Plan to implement a state machine enforcing valid transitions and rejecting invalid state changes at the API level.

---

## 8. File Storage Structure

- Question: The prompt specifies local file storage but does not define directory structure or naming conventions.
- Assumption: Files should be organized by activity ID and material type with unique hashed filenames.
- Solution: Plan to use a structured storage system: /storage/{activity_id}/{material_type}/{file_hash}.

---

## 9. Authentication Session Management

- Question: The prompt defines login security but does not specify session handling (JWT vs server session).
- Assumption: JWT-based stateless authentication is suitable for offline deployment.
- Solution: Plan to implement JWT authentication with expiration and refresh mechanisms.

---

## 10. Access Lock Timing Precision

- Question: The lock rule specifies ≥10 failed attempts within 5 minutes, but does not clarify if attempts reset after success.
- Assumption: Failed attempt counters reset after a successful login.
- Solution: Plan to implement a rolling time window with reset on successful authentication.

---

## 11. Quality Metrics Calculation Frequency

- Question: It is unclear whether metrics (approval rate, correction rate, overspending rate) are computed in real-time or batch.
- Assumption: Metrics should be updated in near real-time after relevant actions.
- Solution: Plan to trigger metric recalculation on key events (review completion, financial update).

---

## 12. Backup and Recovery Scope

- Question: The prompt mentions daily backups but does not define whether files are included or only database records.
- Assumption: Both database and file storage must be included in backups.
- Solution: Plan to implement a scheduled backup process covering PostgreSQL dumps and file system snapshots.

---

## 13. Similarity Check Feature Behavior

- Question: The prompt states the similarity/duplicate check interface is reserved but disabled—should it be accessible?
- Assumption: The interface exists but is hidden or disabled by default.
- Solution: Plan to implement the endpoint and gate it behind a feature flag set to false.

---

## 14. Role-Based Data Masking Rules

- Question: The prompt mentions masking sensitive data but does not define masking levels per role.
- Assumption: Applicants see full data, reviewers see partial masking, admins see full access.
- Solution: Plan to implement role-based serializers that apply masking rules dynamically.

---

## 15. Report Export Format

- Question: The format for exported reports (audit, compliance, reconciliation) is not specified.
- Assumption: CSV and PDF formats are sufficient for offline usage.
- Solution: Plan to implement export functionality supporting CSV and PDF generation.