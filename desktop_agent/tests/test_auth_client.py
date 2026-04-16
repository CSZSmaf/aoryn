from types import SimpleNamespace

import pytest

from desktop_agent.auth_client import AuthAPIClient, AuthAPIError, normalize_auth_api_base_url


def test_normalize_auth_api_base_url_trims_slashes():
    assert normalize_auth_api_base_url(" https://aoryn.org/api/auth/ ") == "https://aoryn.org/api/auth"


def test_auth_client_login_returns_json_payload(monkeypatch):
    def fake_request(method, url, json, headers, timeout):
        assert method == "POST"
        assert url == "https://aoryn.org/api/auth/login"
        assert json == {"email": "user@example.com", "password": "secret"}
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"ok": True, "session": {"access_token": "token"}},
        )

    monkeypatch.setattr("desktop_agent.auth_client.requests.request", fake_request)

    client = AuthAPIClient("https://aoryn.org/api/auth")
    payload = client.login(email="user@example.com", password="secret")

    assert payload["session"]["access_token"] == "token"


def test_auth_client_raises_auth_api_error_for_http_failures(monkeypatch):
    def fake_request(method, url, json, headers, timeout):
        return SimpleNamespace(
            status_code=400,
            json=lambda: {"message": "Email already registered."},
        )

    monkeypatch.setattr("desktop_agent.auth_client.requests.request", fake_request)

    client = AuthAPIClient("https://aoryn.org/api/auth")
    with pytest.raises(AuthAPIError) as exc:
        client.register(email="user@example.com", password="password123", display_name="Aoryn")

    assert exc.value.status_code == 400
    assert "Email already registered." in str(exc.value)
