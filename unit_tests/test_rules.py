import pytest

from app.main import app, decrypt_config_value, parse_bool


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
