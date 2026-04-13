# API Specification

## Auth
- `POST /api/auth/login`
  - Request: `{ "username": "string", "password": "string" }`
  - Response: `{ "access_token": "jwt-token" }`

## Registration
- `POST /api/registrations`
- `GET /api/registrations/{registration_id}`
- `POST /api/registrations/{registration_id}/deadline`
- `POST /api/registrations/{registration_id}/supplementary/start`

## Materials
- `POST /api/materials/upload?registration_id={id}&material_type={type}` (multipart)
- `POST /api/materials/{material_id}/mark-correction`
- `POST /api/materials/{material_id}/supplementary-upload` (multipart)

## Review
- `POST /api/reviews/batch`
- `GET /api/reviews/logs/{registration_id}`

## Finance
- `POST /api/transactions`

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
