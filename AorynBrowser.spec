# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo,
    FixedFileInfo,
    StringFileInfo,
    StringTable,
    StringStruct,
    VarFileInfo,
    VarStruct,
)

from desktop_agent.version import APP_BROWSER_NAME, APP_NAME, APP_PUBLISHER, APP_VERSION


project_root = Path(SPECPATH)
icon_path = project_root / "desktop_agent" / "dashboard_assets" / "icons" / "aoryn-app.ico"

datas = collect_data_files("desktop_agent")
hiddenimports = collect_submodules("desktop_agent")
hiddenimports += collect_submodules("pywinauto")
hiddenimports += collect_submodules("win32com")
hiddenimports += collect_submodules("comtypes")

version_parts = [int(part) for part in APP_VERSION.split(".")]
while len(version_parts) < 4:
    version_parts.append(0)
file_version = tuple(version_parts[:4])

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=file_version,
        prodvers=file_version,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", APP_PUBLISHER),
                        StringStruct("FileDescription", f"{APP_NAME} Browser"),
                        StringStruct("FileVersion", APP_VERSION),
                        StringStruct("InternalName", APP_BROWSER_NAME),
                        StringStruct("OriginalFilename", f"{APP_BROWSER_NAME}.exe"),
                        StringStruct("ProductName", f"{APP_NAME} Browser"),
                        StringStruct("ProductVersion", APP_VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)


a = Analysis(
    ["run_browser.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_BROWSER_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon_path),
    version=version_info,
)
