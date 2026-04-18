from __future__ import annotations

import hashlib
from pathlib import Path

APP_NAME = "Aoryn"
APP_VERSION = "0.1.19"
APP_PUBLISHER = "Aoryn"
APP_ID = "Aoryn.Desktop.Shell"
APP_RELEASE_ARCH = "win64"


def _asset_version_source_paths() -> tuple[Path, ...]:
    assets_root = Path(__file__).resolve().parent / "dashboard_assets"
    return (
        assets_root / "index.html",
        assets_root / "styles.css",
        assets_root / "app.js",
        assets_root / "vendor" / "desktop-markdown.js",
        assets_root / "icons" / "logo-mark.png",
    )


def _compute_asset_revision() -> str:
    digest = hashlib.sha256()
    digest.update(APP_VERSION.encode("utf-8"))
    for path in _asset_version_source_paths():
        digest.update(path.as_posix().encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()[:12]


APP_ASSET_REVISION = _compute_asset_revision()
APP_ASSET_VERSION = f"app-v{APP_VERSION.replace('.', '-')}-{APP_ASSET_REVISION}"


def release_dir_name() -> str:
    return f"{APP_NAME}-{APP_VERSION}-{APP_RELEASE_ARCH}"


def installer_file_name() -> str:
    return f"{APP_NAME}-Setup-{APP_VERSION}.exe"


def portable_zip_file_name() -> str:
    return f"{release_dir_name()}.zip"


def review_zip_file_name() -> str:
    return f"{APP_NAME}-Review-{APP_VERSION}.zip"


def source_zip_file_name() -> str:
    return f"{APP_NAME}-Source-{APP_VERSION}.zip"


def release_manifest_file_name() -> str:
    return "release-manifest.json"


def checksums_file_name() -> str:
    return "SHA256SUMS.txt"
