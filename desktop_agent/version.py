from __future__ import annotations

APP_NAME = "Aoryn"
APP_VERSION = "0.1.7"
APP_PUBLISHER = "Aoryn"
APP_ID = "Aoryn.Desktop.Shell"
APP_RELEASE_ARCH = "win64"
APP_ASSET_REVISION = 10
APP_ASSET_VERSION = f"app-v{APP_VERSION.replace('.', '-')}-r{APP_ASSET_REVISION}"


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
