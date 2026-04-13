import os

import pytest

os.environ.setdefault("SECRET_KEY", "unit-test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ADMIN_BOOTSTRAP_PASSWORD", "unit-test-admin-pass")

from app.main import app, decrypt_config_value, masked_sensitive, parse_bool


def test_app_title():
    assert app.title == "Activity Registration and Funding Audit Platform"


def test_parse_bool_variants():
    assert parse_bool("true") is True
    assert parse_bool("YES") is True
    assert parse_bool("0") is False
    assert parse_bool(None, default=True) is True


def test_decrypt_config_plain_value():
    assert decrypt_config_value("plain_secret", None) == "plain_secret"


def test_decrypt_config_requires_key():
    with pytest.raises(ValueError):
        decrypt_config_value("ENC:abc", None)


def test_masked_sensitive_behavior():
    assert masked_sensitive("AB123456CD") == "AB***CD"
    assert masked_sensitive("1234") == "***"
