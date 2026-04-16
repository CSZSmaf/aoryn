from pathlib import Path

from desktop_agent.release_publish import (
    DEFAULT_LATEST_INSTALLER_KEY,
    build_content_disposition,
    build_pages_env_patch,
    build_public_url,
    installer_object_key,
)


def test_installer_object_key_uses_file_name():
    path = Path("release") / "Aoryn-Setup-0.1.6.exe"
    assert installer_object_key(path) == "Aoryn-Setup-0.1.6.exe"


def test_build_public_url_preserves_nested_key():
    assert (
        build_public_url("https://downloads.aoryn.org/", DEFAULT_LATEST_INSTALLER_KEY)
        == "https://downloads.aoryn.org/latest/Aoryn-Setup-latest.exe"
    )


def test_build_content_disposition_uses_versioned_file_name():
    path = Path("release") / "Aoryn-Setup-0.1.6.exe"
    assert build_content_disposition(path) == 'attachment; filename="Aoryn-Setup-0.1.6.exe"'


def test_build_pages_env_patch_targets_latest_alias():
    payload = build_pages_env_patch(
        "latest/Aoryn-Setup-latest.exe",
        "https://downloads.aoryn.org/latest/Aoryn-Setup-latest.exe",
    )

    production = payload["deployment_configs"]["production"]["env_vars"]
    assert production["AORYN_WINDOWS_INSTALLER_KEY"]["value"] == "latest/Aoryn-Setup-latest.exe"
    assert (
        production["AORYN_WINDOWS_INSTALLER_URL"]["value"]
        == "https://downloads.aoryn.org/latest/Aoryn-Setup-latest.exe"
    )
