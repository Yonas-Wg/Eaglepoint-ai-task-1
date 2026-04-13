import os
from datetime import datetime, timedelta

import pytest
import requests

BASE = os.getenv("BASE_URL", "http://localhost:8000/api")
ROOT = os.getenv("ROOT_URL", "http://localhost:8000")
ADMIN_PASSWORD = os.getenv("ADMIN_TEST_PASSWORD") or os.getenv("ADMIN_BOOTSTRAP_PASSWORD")
REVIEWER_PASSWORD = os.getenv("REVIEWER_TEST_PASSWORD") or os.getenv("REVIEWER_BOOTSTRAP_PASSWORD")
APPLICANT_PASSWORD = os.getenv("APPLICANT_TEST_PASSWORD") or os.getenv("APPLICANT_BOOTSTRAP_PASSWORD")
FINANCE_PASSWORD = os.getenv("FINANCE_TEST_PASSWORD") or os.getenv("FINANCE_BOOTSTRAP_PASSWORD")


def _require_password(password: str | None, env_hint: str) -> str:
    if password:
        return password
    pytest.skip(f"Missing credentials; set {env_hint}")


def _admin_token() -> str:
    password = _require_password(ADMIN_PASSWORD, "ADMIN_TEST_PASSWORD or ADMIN_BOOTSTRAP_PASSWORD")
    response = requests.post(
        f"{BASE}/auth/login",
        json={"username": "admin", "password": password},
        timeout=30,
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    if response.status_code == 423:
        pytest.skip("Admin account is locked in target environment")
    if response.status_code == 401:
        pytest.skip("Admin credentials are invalid for target environment")
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _token_for(username: str, password: str) -> str:
    response = requests.post(
        f"{BASE}/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    if response.status_code == 423:
        pytest.skip(f"{username} account is locked in target environment")
    if response.status_code == 401:
        pytest.skip(f"{username} credentials are invalid for target environment")
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_login_endpoint():
    password = _require_password(ADMIN_PASSWORD, "ADMIN_TEST_PASSWORD or ADMIN_BOOTSTRAP_PASSWORD")
    response = requests.post(
        f"{BASE}/auth/login",
        json={"username": "admin", "password": password},
        timeout=30,
    )
    if response.status_code == 423:
        pytest.skip("Admin account is locked in target environment")
    if response.status_code == 401:
        pytest.skip("Admin credentials are invalid for target environment")
    assert response.status_code == 200


def test_login_invalid_credentials():
    response = requests.post(
        f"{BASE}/auth/login",
        json={"username": "admin", "password": "invalid-password"},
        timeout=30,
    )
    assert response.status_code in (401, 423)


def test_health_endpoint():
    response = requests.get(f"{ROOT}/health", timeout=30)
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_protected_endpoint_requires_token():
    response = requests.get(f"{BASE}/reports/summary", timeout=30)
    assert response.status_code == 401


def test_create_registration_requires_token():
    response = requests.post(
        f"{BASE}/registrations",
        json={"title": "No Token", "id_number": "ID0001", "contact": "0100000000"},
        timeout=30,
    )
    assert response.status_code == 401


def test_create_registration_and_read_reports_with_auth():
    token = _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    create = requests.post(
        f"{BASE}/registrations",
        json={"title": "QA Registration", "id_number": "ID1001", "contact": "0100111222"},
        headers=headers,
        timeout=30,
    )
    assert create.status_code == 200
    summary = requests.get(f"{BASE}/reports/summary", headers=headers, timeout=30)
    assert summary.status_code == 200
    payload = summary.json()
    assert "approval_rate" in payload
    assert "correction_rate" in payload
    assert "overspending_rate" in payload


def test_review_batch_limit_boundary():
    token = _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    too_many = [{"registration_id": 1, "to_state": "Approved", "comment": "bulk"} for _ in range(51)]
    response = requests.post(
        f"{BASE}/reviews/batch",
        json={"items": too_many},
        headers=headers,
        timeout=30,
    )
    assert response.status_code == 400


def test_set_deadline_invalid_datetime_format():
    token = _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    create = requests.post(
        f"{BASE}/registrations",
        json={"title": "Deadline Validation", "id_number": "ID2002", "contact": "0100222333"},
        headers=headers,
        timeout=30,
    )
    assert create.status_code == 200
    reg_id = create.json()["id"]
    response = requests.post(
        f"{BASE}/registrations/{reg_id}/deadline",
        json={"deadline_iso": "not-an-iso-date"},
        headers=headers,
        timeout=30,
    )
    assert response.status_code == 400


def test_review_queue_requires_reviewer_or_admin_role():
    applicant_password = _require_password(APPLICANT_PASSWORD, "APPLICANT_TEST_PASSWORD or APPLICANT_BOOTSTRAP_PASSWORD")
    token = _token_for("applicant", applicant_password)
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE}/reviews/queue?page=1&page_size=20", headers=headers, timeout=30)
    assert response.status_code == 403


def test_review_queue_allows_reviewer_role():
    reviewer_password = _require_password(REVIEWER_PASSWORD, "REVIEWER_TEST_PASSWORD or REVIEWER_BOOTSTRAP_PASSWORD")
    token = _token_for("reviewer", reviewer_password)
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE}/reviews/queue?page=1&page_size=20", headers=headers, timeout=30)
    assert response.status_code == 200
    assert "items" in response.json()


def test_system_backup_requires_admin_role():
    reviewer_password = _require_password(REVIEWER_PASSWORD, "REVIEWER_TEST_PASSWORD or REVIEWER_BOOTSTRAP_PASSWORD")
    token = _token_for("reviewer", reviewer_password)
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(f"{BASE}/system/backup", headers=headers, timeout=30)
    assert response.status_code == 403


def test_reports_export_requires_privileged_role():
    applicant_password = _require_password(APPLICANT_PASSWORD, "APPLICANT_TEST_PASSWORD or APPLICANT_BOOTSTRAP_PASSWORD")
    token = _token_for("applicant", applicant_password)
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE}/reports/audit/export?format=csv", headers=headers, timeout=30)
    assert response.status_code == 403


def test_material_checklist_flow_pending_to_submitted():
    token = _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    create = requests.post(
        f"{BASE}/registrations",
        json={"title": "Checklist Flow", "id_number": "ID3003", "contact": "0100333444"},
        headers=headers,
        timeout=30,
    )
    assert create.status_code == 200
    reg_id = create.json()["id"]

    checklist = requests.get(f"{BASE}/materials/checklist/{reg_id}", headers=headers, timeout=30)
    assert checklist.status_code == 200
    initial_items = checklist.json()["items"]
    assert any(item["material_type"] == "proposal" and item["status_label"] == "Pending Submission" for item in initial_items)

    files = {"upload": ("proposal.pdf", b"proposal-bytes", "application/pdf")}
    upload = requests.post(
        f"{BASE}/materials/upload?registration_id={reg_id}&material_type=proposal",
        headers=headers,
        files=files,
        timeout=30,
    )
    assert upload.status_code == 200

    checklist_after = requests.get(f"{BASE}/materials/checklist/{reg_id}", headers=headers, timeout=30)
    assert checklist_after.status_code == 200
    updated_items = checklist_after.json()["items"]
    assert any(item["material_type"] == "proposal" and item["status_label"] == "Submitted" for item in updated_items)


def test_budget_required_and_overspending_confirmation():
    token = _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    create = requests.post(
        f"{BASE}/registrations",
        json={"title": "Budget Flow", "id_number": "ID4004", "contact": "0100444555"},
        headers=headers,
        timeout=30,
    )
    assert create.status_code == 200
    reg_id = create.json()["id"]

    without_budget = requests.post(
        f"{BASE}/transactions",
        json={"registration_id": reg_id, "tx_type": "expense", "category": "ops", "amount": 100},
        headers=headers,
        timeout=30,
    )
    assert without_budget.status_code == 400

    set_budget = requests.post(
        f"{BASE}/funding/{reg_id}/budget",
        json={"budget": 100},
        headers=headers,
        timeout=30,
    )
    assert set_budget.status_code == 200

    over_budget_without_confirm = requests.post(
        f"{BASE}/transactions",
        json={"registration_id": reg_id, "tx_type": "expense", "category": "ops", "amount": 120, "secondary_confirmation": False},
        headers=headers,
        timeout=30,
    )
    assert over_budget_without_confirm.status_code == 400

    over_budget_with_confirm = requests.post(
        f"{BASE}/transactions",
        json={"registration_id": reg_id, "tx_type": "expense", "category": "ops", "amount": 120, "secondary_confirmation": True},
        headers=headers,
        timeout=30,
    )
    assert over_budget_with_confirm.status_code == 200


def test_reports_summary_requires_privileged_role():
    applicant_password = _require_password(APPLICANT_PASSWORD, "APPLICANT_TEST_PASSWORD or APPLICANT_BOOTSTRAP_PASSWORD")
    token = _token_for("applicant", applicant_password)
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE}/reports/summary", headers=headers, timeout=30)
    assert response.status_code == 403


def test_supplementary_upload_allowed_within_window_even_after_deadline():
    token = _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    create = requests.post(
        f"{BASE}/registrations",
        json={"title": "Supplementary Flow", "id_number": "ID5005", "contact": "0100555666"},
        headers=headers,
        timeout=30,
    )
    assert create.status_code == 200
    reg_id = create.json()["id"]

    initial_upload = requests.post(
        f"{BASE}/materials/upload?registration_id={reg_id}&material_type=proposal",
        headers=headers,
        files={"upload": ("proposal.pdf", b"v1", "application/pdf")},
        timeout=30,
    )
    assert initial_upload.status_code == 200
    material_id = initial_upload.json()["id"]

    past_deadline = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
    set_deadline = requests.post(
        f"{BASE}/registrations/{reg_id}/deadline",
        json={"deadline_iso": past_deadline},
        headers=headers,
        timeout=30,
    )
    assert set_deadline.status_code == 200

    mark_correction = requests.post(
        f"{BASE}/materials/{material_id}/mark-correction",
        json={"reason": "fix and reupload"},
        headers=headers,
        timeout=30,
    )
    assert mark_correction.status_code == 200

    start_supplementary = requests.post(
        f"{BASE}/registrations/{reg_id}/supplementary/start",
        headers=headers,
        timeout=30,
    )
    assert start_supplementary.status_code == 200

    reupload = requests.post(
        f"{BASE}/materials/{material_id}/supplementary-upload",
        headers=headers,
        files={"upload": ("proposal_v2.pdf", b"v2", "application/pdf")},
        timeout=30,
    )
    assert reupload.status_code == 200


def test_reviewer_review_logs_require_assigned_scope():
    reviewer_password = _require_password(REVIEWER_PASSWORD, "REVIEWER_TEST_PASSWORD or REVIEWER_BOOTSTRAP_PASSWORD")
    admin_token = _admin_token()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    reviewer_token = _token_for("reviewer", reviewer_password)
    reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}

    create = requests.post(
        f"{BASE}/registrations",
        json={"title": "Review Scope", "id_number": "ID6006", "contact": "0100666777"},
        headers=admin_headers,
        timeout=30,
    )
    assert create.status_code == 200
    reg_id = create.json()["id"]

    denied = requests.get(f"{BASE}/reviews/logs/{reg_id}", headers=reviewer_headers, timeout=30)
    assert denied.status_code == 403

    assign = requests.post(
        f"{BASE}/access/assign",
        json={"registration_id": reg_id, "username": "reviewer", "domain": "review"},
        headers=admin_headers,
        timeout=30,
    )
    assert assign.status_code == 200

    allowed = requests.get(f"{BASE}/reviews/logs/{reg_id}", headers=reviewer_headers, timeout=30)
    assert allowed.status_code == 200


def test_finance_budget_requires_assigned_scope():
    finance_password = _require_password(FINANCE_PASSWORD, "FINANCE_TEST_PASSWORD or FINANCE_BOOTSTRAP_PASSWORD")
    admin_token = _admin_token()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    finance_token = _token_for("finance", finance_password)
    finance_headers = {"Authorization": f"Bearer {finance_token}"}

    create = requests.post(
        f"{BASE}/registrations",
        json={"title": "Finance Scope", "id_number": "ID7007", "contact": "0100777888"},
        headers=admin_headers,
        timeout=30,
    )
    assert create.status_code == 200
    reg_id = create.json()["id"]

    denied = requests.post(
        f"{BASE}/funding/{reg_id}/budget",
        json={"budget": 1000},
        headers=finance_headers,
        timeout=30,
    )
    assert denied.status_code == 403

    assign = requests.post(
        f"{BASE}/access/assign",
        json={"registration_id": reg_id, "username": "finance", "domain": "finance"},
        headers=admin_headers,
        timeout=30,
    )
    assert assign.status_code == 200

    allowed = requests.post(
        f"{BASE}/funding/{reg_id}/budget",
        json={"budget": 1000},
        headers=finance_headers,
        timeout=30,
    )
    assert allowed.status_code == 200
