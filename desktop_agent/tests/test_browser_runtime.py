from __future__ import annotations

import shutil
import sys
from pathlib import Path
from uuid import uuid4

from desktop_agent import browser_runtime


def test_resolve_installed_browser_prefers_adjacent_executable(monkeypatch):
    temp_root = Path("test_artifacts") / f"browser_runtime_adjacent_{uuid4().hex}"
    try:
        app_dir = temp_root / "app"
        app_dir.mkdir(parents=True)
        main_exe = app_dir / "Aoryn.exe"
        main_exe.write_bytes(b"core")
        browser_exe = app_dir / "AorynBrowser.exe"
        browser_exe.write_bytes(b"browser")

        monkeypatch.setattr(sys, "executable", str(main_exe))

        assert browser_runtime._resolve_installed_browser_executable() == browser_exe.resolve()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_resolve_installed_browser_uses_registry_install_dir(monkeypatch):
    temp_root = Path("test_artifacts") / f"browser_runtime_registry_{uuid4().hex}"
    try:
        app_dir = temp_root / "app"
        app_dir.mkdir(parents=True)
        main_exe = app_dir / "Aoryn.exe"
        main_exe.write_bytes(b"core")

        browser_dir = temp_root / "browser"
        browser_dir.mkdir()
        browser_exe = browser_dir / "AorynBrowser.exe"
        browser_exe.write_bytes(b"browser")

        monkeypatch.setattr(sys, "executable", str(main_exe))
        monkeypatch.setattr(browser_runtime, "_browser_registry_install_dir", lambda: browser_dir.resolve())

        assert browser_runtime._resolve_installed_browser_executable() == browser_exe.resolve()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_installed_browser_candidates_include_default_install_dir(monkeypatch):
    temp_root = Path("test_artifacts") / f"browser_runtime_candidates_{uuid4().hex}"
    try:
        temp_root.mkdir(parents=True)
        monkeypatch.setattr(browser_runtime, "_browser_registry_install_dir", lambda: None)
        monkeypatch.setenv("LOCALAPPDATA", str(temp_root))

        candidates = browser_runtime._installed_browser_candidates()
        expected = temp_root / "Programs" / "Aoryn Browser" / "AorynBrowser.exe"

        assert expected in candidates
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
