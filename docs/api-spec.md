# API Specification

## Auth
- `POST /api/auth/login`
  - Request: `{ "username": "string", "password": "string" }`
  - Response: `{ "access_token": "jwt-token" }`

## Registration
- `POST /api/registrations`
  - Request: `{ "title": "string", "id_number": "string", "contact": "string" }` (applicant identity is derived from token)
- `GET /api/registrations/{registration_id}`
- `POST /api/registrations/{registration_id}/deadline`
- `POST /api/registrations/{registration_id}/supplementary/start`

## Materials
- `POST /api/materials/upload?registration_id={id}&material_type={type}` (multipart)
- `POST /api/materials/{material_id}/mark-correction`
- `POST /api/materials/{material_id}/supplementary-upload` (multipart)

## Review
- `POST /api/reviews/batch`
  - Request: `{ "items": [{ "registration_id": 1, "to_state": "Approved", "comment": "ok" }] }` (reviewer identity is derived from token)
- `GET /api/reviews/logs/{registration_id}`

## Finance
- `POST /api/transactions`
- `POST /api/transactions/{transaction_id}/invoice` (multipart)
- `GET /api/transactions/stats?registration_id={id}&start_iso={iso}&end_iso={iso}`

## Reports
- `GET /api/reports/summary`
- `GET /api/reports/{report_type}/export?format=csv|pdf`

## System
- `GET /api/similarity-check` (disabled by default)
- `GET /api/whitelist-policies/export`
- `POST /api/batches`
- `POST /api/system/backup`
- `POST /api/system/recovery`

## Error format
- Structured error detail: `{"code": <http-code>, "msg": "error message"}`
