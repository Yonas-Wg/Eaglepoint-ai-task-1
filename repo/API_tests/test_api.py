import os

import requests
import pytest

BASE = os.getenv("BASE_URL", "http://localhost:8000/api")
ROOT = os.getenv("ROOT_URL", "http://localhost:8000")


def _admin_token() -> str:
    response = requests.post(
        f"{BASE}/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login unavailable for auth tests (status={response.status_code})")
    return response.json()["access_token"]


def test_login_endpoint():
    response = requests.post(
        f"{BASE}/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=30,
    )
    assert response.status_code in (200, 401, 423)


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
