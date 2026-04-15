import json
import shutil
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from desktop_agent.release_bundle import build_release_artifacts, iter_source_snapshot_files
from desktop_agent.version import (
    checksums_file_name,
    installer_file_name,
    portable_zip_file_name,
    release_dir_name,
    release_manifest_file_name,
    review_zip_file_name,
    source_zip_file_name,
)


def test_iter_source_snapshot_files_excludes_build_outputs():
    project_root = Path("test_artifacts") / f"release_bundle_iter_{uuid4().hex}"
    (project_root / "desktop_agent").mkdir(parents=True)
    (project_root / "build").mkdir()
    (project_root / "dist").mkdir()
    (project_root / "runs").mkdir()
    (project_root / "release").mkdir()
    (project_root / "__pycache__").mkdir()
    (project_root / "desktop_agent" / "module.py").write_text("print('ok')\n", encoding="utf-8")
    (project_root / "README.md").write_text("readme", encoding="utf-8")
    (project_root / "build" / "temp.txt").write_text("skip", encoding="utf-8")
    (project_root / "runs" / "ui_smoke_dashboard.png").write_text("skip", encoding="utf-8")
    (project_root / "__pycache__" / "x.pyc").write_bytes(b"skip")

    try:
        files = [path.relative_to(project_root).as_posix() for path in iter_source_snapshot_files(project_root)]

        assert "desktop_agent/module.py" in files
        assert "README.md" in files
        assert "build/temp.txt" not in files
        assert "runs/ui_smoke_dashboard.png" not in files
        assert "__pycache__/x.pyc" not in files
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_build_release_artifacts_creates_review_bundle():
    project_root = Path("test_artifacts") / f"release_bundle_build_{uuid4().hex}"
    release_root = project_root / "release"
    release_dir = release_root / release_dir_name()
    installer_path = release_root / installer_file_name()

    (project_root / "desktop_agent").mkdir(parents=True)
    release_dir.mkdir(parents=True)
    (release_dir / "Aoryn.exe").write_bytes(b"exe")
    (release_dir / "_internal").mkdir()
    (release_dir / "_internal" / "payload.txt").write_text("payload", encoding="utf-8")
    installer_path.write_bytes(b"installer")
    (project_root / "README.md").write_text("cn readme", encoding="utf-8")
    (project_root / "README.en.md").write_text("en readme", encoding="utf-8")
    (project_root / "desktop_agent" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (project_root / "runs").mkdir()
    (project_root / "runs" / "ui_smoke_dashboard.png").write_text("old screenshot", encoding="utf-8")

    try:
        payload = build_release_artifacts(
            project_root=project_root,
            release_root=release_root,
            release_dir=release_dir,
            installer_path=installer_path,
        )

        portable_zip = release_root / portable_zip_file_name()
        source_zip = release_root / source_zip_file_name()
        review_zip = release_root / review_zip_file_name()
        manifest_path = release_root / release_manifest_file_name()
        checksums_path = release_root / checksums_file_name()

        assert Path(payload["portable_zip"]) == portable_zip
        assert Path(payload["source_zip"]) == source_zip
        assert Path(payload["review_zip"]) == review_zip
        assert portable_zip.exists()
        assert source_zip.exists()
        assert review_zip.exists()
        assert manifest_path.exists()
        assert checksums_path.exists()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["distribution"]["primary_installer"] == installer_path.name
        assert manifest["distribution"]["portable_zip"] == portable_zip.name
        assert manifest["distribution"]["source_snapshot"] == source_zip.name
        assert manifest["distribution"]["review_bundle"] == review_zip.name
        assert "runs" in manifest["source_snapshot_policy"]["excluded_directories"]

        checksums = checksums_path.read_text(encoding="utf-8")
        assert installer_path.name in checksums
        assert portable_zip.name in checksums
        assert source_zip.name in checksums
        assert manifest_path.name in checksums

        with ZipFile(source_zip) as archive:
            source_members = archive.namelist()
            assert any(member.endswith("README.md") for member in source_members)
            assert any(member.endswith("desktop_agent/app.py") for member in source_members)
            assert all("/release/" not in member for member in source_members)
            assert all("/runs/" not in member for member in source_members)
            assert all("ui_smoke_dashboard.png" not in member for member in source_members)

        with ZipFile(review_zip) as archive:
            review_members = set(archive.namelist())
            assert installer_path.name in review_members
            assert portable_zip.name in review_members
            assert source_zip.name in review_members
            assert manifest_path.name in review_members
            assert checksums_path.name in review_members
            assert "README.md" in review_members
            assert "README.en.md" in review_members
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
