import shutil
from pathlib import Path
from uuid import uuid4

from desktop_agent.auth_state import AuthSessionStore


def test_auth_session_store_roundtrip():
    temp_root = Path(__file__).resolve().parents[2] / ".pytest-local" / f"aoryn-auth-store-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        store = AuthSessionStore(temp_root / "auth-session.json")

        payload = store.save_payload(
            {
                "api_base_url": "https://aoryn.org/api/auth",
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_at": 1234567890,
                "profile": {
                    "id": "user-1",
                    "email": "user@example.com",
                    "display_name": "Aoryn User",
                    "created_at": "2026-04-16T10:00:00Z",
                },
            }
        )

        loaded = store.load_payload()
        snapshot = store.snapshot()

        assert payload["api_base_url"] == "https://aoryn.org/api/auth"
        assert loaded["access_token"] == "access-token"
        assert loaded["refresh_token"] == "refresh-token"
        assert snapshot["authenticated"] is True
        assert snapshot["email"] == "user@example.com"
        assert snapshot["display_name"] == "Aoryn User"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_auth_session_store_clear_resets_snapshot():
    temp_root = Path(__file__).resolve().parents[2] / ".pytest-local" / f"aoryn-auth-store-clear-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        store = AuthSessionStore(temp_root / "auth-session.json")
        store.save_payload(
            {
                "api_base_url": "https://aoryn.org/api/auth",
                "access_token": "token",
                "refresh_token": "refresh",
                "expires_at": 123,
                "profile": {"email": "user@example.com"},
            }
        )

        store.clear()

        assert store.load_payload() is None
        assert store.snapshot()["authenticated"] is False
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
