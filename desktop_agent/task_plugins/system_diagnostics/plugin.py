from __future__ import annotations

import json
import os
import platform
import shutil
import socket
from datetime import datetime
from pathlib import Path
from typing import Any

from desktop_agent.plugin_runtime import PluginManifest, PluginRunResult
from desktop_agent.task_plugins import office_common


_PLUGIN_TERMS = ("系统诊断插件", "system diagnostics", "diagnose system", "windows snapshot")
_SYSTEM_TERMS = ("系统", "电脑", "windows", "system", "computer", "environment")
_DIAG_TERMS = ("诊断", "快照", "状态", "检查", "diagnostic", "diagnose", "snapshot", "status", "check")


def match_task(task: str, *, manifest: PluginManifest, config: Any | None = None) -> bool:
    text = str(task or "")
    lowered = text.lower()
    if any(term.lower() in lowered for term in _PLUGIN_TERMS):
        return True
    has_system = any(term.lower() in lowered for term in _SYSTEM_TERMS)
    has_diag = any(term.lower() in lowered for term in _DIAG_TERMS)
    return has_system and has_diag


def status(*, manifest: PluginManifest, config: Any | None = None) -> dict[str, Any]:
    return {
        "state": "available",
        "label": "File output",
        "detail": "Collects a local Windows/Python snapshot without external services.",
    }


def run_task(
    task: str,
    context: Any,
    *,
    manifest: PluginManifest,
    config: Any | None = None,
) -> PluginRunResult:
    output_dir = office_common.resolve_output_dir(context)
    json_path = output_dir / "Aoryn_System_Diagnostics.json"
    actions = office_common.emit(context, "系统诊断插件正在收集本机环境快照")

    snapshot = _collect_snapshot()
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    office_common.copy_to_run_dir(json_path, context)
    report_path = office_common.write_text_artifact(
        context,
        "Aoryn_System_Diagnostics.md",
        _markdown_report(task=task, snapshot=snapshot, json_path=json_path),
    )
    office_common.open_artifacts(context, (report_path, json_path))

    answer = (
        "系统诊断插件任务已完成：已生成 Markdown 诊断报告和 JSON 快照。\n\n"
        f"报告：{report_path}\n"
        f"JSON：{json_path}"
    )
    return PluginRunResult(
        completed=True,
        headline="系统诊断插件已完成：生成本机环境快照",
        answer=answer,
        actions=actions,
        artifacts=[report_path.name, json_path.name],
    )


def _collect_snapshot() -> dict[str, Any]:
    memory = _memory_snapshot()
    disks = []
    for root in _drive_roots():
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue
        disks.append(
            {
                "root": str(root),
                "total_gb": round(usage.total / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
            }
        )
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "memory": memory,
        "disks": disks,
        "apps": _app_snapshot(),
    }


def _memory_snapshot() -> dict[str, Any]:
    try:
        import psutil  # type: ignore

        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "percent_used": mem.percent,
        }
    except Exception:
        return {"status": "psutil unavailable"}


def _drive_roots() -> list[Path]:
    if os.name != "nt":
        return [Path("/")]
    roots: list[Path] = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:/")
        if root.exists():
            roots.append(root)
    return roots


def _app_snapshot() -> dict[str, str | None]:
    names = {
        "python": "python",
        "notepad": "notepad.exe",
        "paint": "mspaint.exe",
        "calculator": "calc.exe",
        "powershell": "powershell.exe",
    }
    return {label: shutil.which(command) for label, command in names.items()}


def _markdown_report(*, task: str, snapshot: dict[str, Any], json_path: Path) -> str:
    disks = snapshot.get("disks") if isinstance(snapshot.get("disks"), list) else []
    disk_lines = "\n".join(
        f"- {disk.get('root')}: total {disk.get('total_gb')} GB, free {disk.get('free_gb')} GB"
        for disk in disks
    ) or "- 未读取到磁盘信息"
    apps = snapshot.get("apps") if isinstance(snapshot.get("apps"), dict) else {}
    app_lines = "\n".join(f"- {name}: `{path or 'not found in PATH'}`" for name, path in apps.items())
    memory = snapshot.get("memory") if isinstance(snapshot.get("memory"), dict) else {}
    return (
        "# 系统诊断插件报告\n\n"
        "## 任务\n\n"
        f"{task}\n\n"
        "## 基础环境\n\n"
        f"- 主机：{snapshot.get('host')}\n"
        f"- 系统：{snapshot.get('platform')}\n"
        f"- Python：{snapshot.get('python')}\n"
        f"- CPU 核心数：{snapshot.get('cpu_count')}\n"
        f"- 内存：{memory}\n\n"
        "## 磁盘\n\n"
        f"{disk_lines}\n\n"
        "## 常用程序路径\n\n"
        f"{app_lines}\n\n"
        "## 产物\n\n"
        f"- JSON 快照：`{json_path}`\n"
    )
