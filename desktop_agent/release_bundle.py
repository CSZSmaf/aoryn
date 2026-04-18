from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from desktop_agent.version import (
    APP_BROWSER_DISPLAY_NAME,
    APP_NAME,
    APP_PUBLISHER,
    APP_RELEASE_ARCH,
    APP_VERSION,
    browser_installer_file_name,
    browser_portable_zip_file_name,
    browser_release_dir_name,
    checksums_file_name,
    installer_file_name,
    portable_zip_file_name,
    release_manifest_file_name,
    review_zip_file_name,
    source_zip_file_name,
)

SOURCE_EXCLUDED_DIRS = {
    ".git",
    ".tmp",
    ".pytest_cache",
    ".pytest-local",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    "build",
    "dist",
    "logs",
    "release",
    "runs",
    "test_artifacts",
    "pytest_temp",
}
SOURCE_EXCLUDED_FILES = {
    ".DS_Store",
    "Thumbs.db",
}
SOURCE_EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".log",
}


def iter_source_snapshot_files(project_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in project_root.rglob("*"):
        if path.is_dir():
            continue
        if _should_exclude_source_path(project_root, path):
            continue
        files.append(path)
    return sorted(files)


def build_release_manifest(
    *,
    release_dir_name: str,
    browser_release_dir_name: str,
    installer_name: str,
    browser_installer_name: str,
    portable_zip_name: str,
    browser_portable_zip_name: str,
    source_zip_name: str,
    review_zip_name: str,
    checksums_name: str,
    manifest_name: str,
) -> dict[str, object]:
    return {
        "app_name": APP_NAME,
        "browser_name": APP_BROWSER_DISPLAY_NAME,
        "publisher": APP_PUBLISHER,
        "version": APP_VERSION,
        "platform": APP_RELEASE_ARCH,
        "build_time_utc": datetime.now(timezone.utc).isoformat(),
        "distribution": {
            "primary_installer": installer_name,
            "browser_installer": browser_installer_name,
            "portable_directory": release_dir_name,
            "browser_portable_directory": browser_release_dir_name,
            "portable_zip": portable_zip_name,
            "browser_portable_zip": browser_portable_zip_name,
            "review_bundle": review_zip_name,
            "source_snapshot": source_zip_name,
        },
        "install_policy": {
            "custom_install_dir": True,
            "desktop_default_install_dir": rf"%LOCALAPPDATA%\Programs\{APP_NAME}",
            "browser_default_install_dir": rf"%LOCALAPPDATA%\Programs\{APP_BROWSER_DISPLAY_NAME}",
            "config_dir": rf"%APPDATA%\{APP_NAME}",
            "data_dir": rf"%LOCALAPPDATA%\{APP_NAME}",
            "run_root": rf"%LOCALAPPDATA%\{APP_NAME}\runs",
            "cache_dir": rf"%LOCALAPPDATA%\{APP_NAME}\cache",
            "uninstall_user_data_prompt": True,
        },
        "source_snapshot_policy": {
            "description": "Code and packaged assets only. Runtime history, screenshots, logs, caches, and local workspace traces are excluded from the reviewable source snapshot.",
            "excluded_directories": sorted(
                [
                    ".git",
                    ".tmp",
                    ".pytest_cache",
                    ".pytest-local",
                    ".ruff_cache",
                    ".mypy_cache",
                    "__pycache__",
                    "build",
                    "dist",
                    "logs",
                    "release",
                    "runs",
                    "test_artifacts",
                    "pytest_temp",
                ]
            ),
        },
        "review_bundle_contents": [
            installer_name,
            browser_installer_name,
            portable_zip_name,
            browser_portable_zip_name,
            source_zip_name,
            manifest_name,
            checksums_name,
            "README.md",
            "README.en.md",
        ],
    }


def build_release_artifacts(
    *,
    project_root: Path,
    release_root: Path,
    release_dir: Path,
    browser_release_dir: Path,
    installer_path: Path,
    browser_installer_path: Path,
) -> dict[str, object]:
    release_root.mkdir(parents=True, exist_ok=True)
    portable_zip_path = release_root / portable_zip_file_name()
    browser_portable_zip_path = release_root / browser_portable_zip_file_name()
    source_zip_path = release_root / source_zip_file_name()
    review_zip_path = release_root / review_zip_file_name()
    manifest_path = release_root / release_manifest_file_name()
    checksums_path = release_root / checksums_file_name()

    for target in (
        portable_zip_path,
        browser_portable_zip_path,
        source_zip_path,
        review_zip_path,
        manifest_path,
        checksums_path,
    ):
        target.unlink(missing_ok=True)

    zip_directory(release_dir, portable_zip_path, root_name=release_dir.name)
    zip_directory(browser_release_dir, browser_portable_zip_path, root_name=browser_release_dir.name)
    zip_paths(
        source_zip_path,
        (
            (path, Path(source_zip_path.stem) / path.relative_to(project_root))
            for path in iter_source_snapshot_files(project_root)
        ),
    )

    manifest = build_release_manifest(
        release_dir_name=release_dir.name,
        browser_release_dir_name=browser_release_dir.name,
        installer_name=installer_path.name,
        browser_installer_name=browser_installer_path.name,
        portable_zip_name=portable_zip_path.name,
        browser_portable_zip_name=browser_portable_zip_path.name,
        source_zip_name=source_zip_path.name,
        review_zip_name=review_zip_path.name,
        checksums_name=checksums_path.name,
        manifest_name=manifest_path.name,
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    checksum_entries = [
        installer_path,
        browser_installer_path,
        portable_zip_path,
        browser_portable_zip_path,
        source_zip_path,
        manifest_path,
        project_root / "README.md",
        project_root / "README.en.md",
    ]
    write_sha256_sums(checksums_path, checksum_entries)

    zip_paths(
        review_zip_path,
        [
            (installer_path, Path(installer_path.name)),
            (browser_installer_path, Path(browser_installer_path.name)),
            (portable_zip_path, Path(portable_zip_path.name)),
            (browser_portable_zip_path, Path(browser_portable_zip_path.name)),
            (source_zip_path, Path(source_zip_path.name)),
            (manifest_path, Path(manifest_path.name)),
            (checksums_path, Path(checksums_path.name)),
            (project_root / "README.md", Path("README.md")),
            (project_root / "README.en.md", Path("README.en.md")),
        ],
    )

    return {
        "installer": str(installer_path),
        "browser_installer": str(browser_installer_path),
        "portable_directory": str(release_dir),
        "browser_portable_directory": str(browser_release_dir),
        "portable_zip": str(portable_zip_path),
        "browser_portable_zip": str(browser_portable_zip_path),
        "source_zip": str(source_zip_path),
        "review_zip": str(review_zip_path),
        "manifest": str(manifest_path),
        "checksums": str(checksums_path),
    }


def zip_directory(source_dir: Path, output_path: Path, *, root_name: str | None = None) -> None:
    root = Path(root_name) if root_name else Path(source_dir.name)
    zip_paths(
        output_path,
        (
            (path, root / path.relative_to(source_dir))
            for path in sorted(source_dir.rglob("*"))
            if path.is_file()
        ),
    )


def zip_paths(output_path: Path, items) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        for source_path, archive_path in items:
            source = Path(source_path)
            archive.write(source, arcname=str(Path(archive_path).as_posix()))


def write_sha256_sums(output_path: Path, paths: list[Path]) -> None:
    lines = []
    for path in paths:
        if not path.exists():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest} *{path.name}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _should_exclude_source_path(project_root: Path, path: Path) -> bool:
    relative = path.relative_to(project_root)
    if any(part in SOURCE_EXCLUDED_DIRS or part.startswith("pytest-cache-files") for part in relative.parts):
        return True
    if path.name in SOURCE_EXCLUDED_FILES:
        return True
    if path.suffix.lower() in SOURCE_EXCLUDED_SUFFIXES:
        return True
    return False
