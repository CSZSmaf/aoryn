from __future__ import annotations

import base64
import ctypes
import json
import sys
import time
from pathlib import Path
from typing import Any


if sys.platform == "win32":
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32


def _blob_from_bytes(data: bytes) -> tuple["_DATA_BLOB", Any]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DATA_BLOB(
        cbData=len(data),
        pbData=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    return blob, buffer


def _bytes_from_blob(blob: "_DATA_BLOB") -> bytes:
    if not blob.cbData or not blob.pbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def _protect_bytes(data: bytes) -> tuple[str, str]:
    if sys.platform != "win32":
        return "plain", base64.b64encode(data).decode("ascii")

    input_blob, input_buffer = _blob_from_bytes(data)
    output_blob = _DATA_BLOB()
    if not _crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "Aoryn Auth Session",
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise OSError("Unable to protect the auth session with Windows DPAPI.")
    try:
        _ = input_buffer
        return "dpapi", base64.b64encode(_bytes_from_blob(output_blob)).decode("ascii")
    finally:
        if output_blob.pbData:
            _kernel32.LocalFree(output_blob.pbData)


def _unprotect_bytes(storage_format: str, payload: str) -> bytes:
    raw = base64.b64decode(payload.encode("ascii"))
    if storage_format != "dpapi" or sys.platform != "win32":
        return raw

    input_blob, input_buffer = _blob_from_bytes(raw)
    output_blob = _DATA_BLOB()
    if not _crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise OSError("Unable to read the auth session from Windows DPAPI.")
    try:
        _ = input_buffer
        return _bytes_from_blob(output_blob)
    finally:
        if output_blob.pbData:
            _kernel32.LocalFree(output_blob.pbData)


def _normalize_profile(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "id": str(raw.get("id") or "").strip() or None,
        "email": str(raw.get("email") or "").strip() or None,
        "display_name": str(raw.get("display_name") or "").strip() or None,
        "created_at": raw.get("created_at"),
    }


class AuthSessionStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_payload(self) -> dict[str, Any] | None:
        try:
            envelope = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return None

        if not isinstance(envelope, dict):
            return None

        payload = str(envelope.get("payload") or "").strip()
        if not payload:
            return None

        storage_format = str(envelope.get("format") or "plain").strip() or "plain"
        try:
            decoded = _unprotect_bytes(storage_format, payload)
            data = json.loads(decoded.decode("utf-8"))
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        return {
            "api_base_url": str(data.get("api_base_url") or "").strip() or None,
            "access_token": str(data.get("access_token") or "").strip() or None,
            "refresh_token": str(data.get("refresh_token") or "").strip() or None,
            "expires_at": data.get("expires_at"),
            "stored_at": data.get("stored_at"),
            "profile": _normalize_profile(data.get("profile")),
        }

    def save_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile = _normalize_profile(payload.get("profile"))
        clean = {
            "api_base_url": str(payload.get("api_base_url") or "").strip() or None,
            "access_token": str(payload.get("access_token") or "").strip() or None,
            "refresh_token": str(payload.get("refresh_token") or "").strip() or None,
            "expires_at": payload.get("expires_at"),
            "stored_at": payload.get("stored_at") if isinstance(payload.get("stored_at"), (int, float)) else time.time(),
            "profile": profile,
        }
        serialized = json.dumps(clean, ensure_ascii=False).encode("utf-8")
        storage_format, encoded = _protect_bytes(serialized)
        envelope = {
            "version": 1,
            "format": storage_format,
            "payload": encoded,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        return clean

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)

    def snapshot(self) -> dict[str, Any]:
        payload = self.load_payload()
        if not payload:
            return {
                "authenticated": False,
                "api_base_url": None,
                "profile": None,
                "expires_at": None,
                "stored_at": None,
            }

        profile = payload.get("profile") or {}
        return {
            "authenticated": True,
            "api_base_url": payload.get("api_base_url"),
            "profile": profile,
            "email": profile.get("email"),
            "display_name": profile.get("display_name"),
            "created_at": profile.get("created_at"),
            "expires_at": payload.get("expires_at"),
            "stored_at": payload.get("stored_at"),
        }
