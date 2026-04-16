from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


def normalize_auth_api_base_url(base_url: str | None) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("Auth API base URL is required.")
    return value


@dataclass(slots=True)
class AuthAPIError(Exception):
    message: str
    status_code: int | None = None
    payload: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


class AuthAPIClient:
    def __init__(self, base_url: str, *, timeout: float = 15.0) -> None:
        self.base_url = normalize_auth_api_base_url(base_url)
        self.timeout = float(timeout)

    def register(self, *, email: str, password: str, display_name: str) -> dict[str, Any]:
        return self._post(
            "/register",
            {
                "email": email,
                "password": password,
                "displayName": display_name,
            },
        )

    def login(self, *, email: str, password: str) -> dict[str, Any]:
        return self._post(
            "/login",
            {
                "email": email,
                "password": password,
            },
        )

    def logout(self, *, access_token: str) -> dict[str, Any]:
        return self._post(
            "/logout",
            {},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    def me(self, *, access_token: str) -> dict[str, Any]:
        return self._get(
            "/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    def refresh(self, *, refresh_token: str) -> dict[str, Any]:
        return self._post(
            "/refresh",
            {
                "refreshToken": refresh_token,
            },
        )

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._request("POST", path, payload=payload, headers=headers)

    def _get(self, path: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        return self._request("GET", path, headers=headers)

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AuthAPIError("Unable to reach the authentication service.") from exc

        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.status_code >= 400:
            message = (
                str(data.get("message") or "").strip()
                or str(data.get("error") or "").strip()
                or "Authentication request failed."
            )
            raise AuthAPIError(message=message, status_code=response.status_code, payload=data or None)
        if not isinstance(data, dict):
            return {}
        return data
