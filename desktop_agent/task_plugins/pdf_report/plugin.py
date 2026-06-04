from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from desktop_agent.plugin_runtime import PluginManifest, PluginRunResult
from desktop_agent.task_plugins import office_common


_PLUGIN_TERMS = ("pdf 插件", "pdf plugin")
_PDF_TERMS = ("pdf", "PDF")
_REPORT_TERMS = ("报告", "总结", "交付", "report", "summary", "deliverable", "presentation")


def match_task(task: str, *, manifest: PluginManifest, config: Any | None = None) -> bool:
    text = str(task or "")
    lowered = text.lower()
    if any(term.lower() in lowered for term in _PLUGIN_TERMS):
        return True
    has_pdf = any(term.lower() in lowered for term in _PDF_TERMS)
    has_report = any(term.lower() in lowered for term in _REPORT_TERMS)
    return has_pdf and has_report


def status(*, manifest: PluginManifest, config: Any | None = None) -> dict[str, Any]:
    return {
        "state": "available",
        "label": "File output",
        "detail": "Creates a dependency-free PDF fallback plus a Markdown trace report.",
    }


def run_task(
    task: str,
    context: Any,
    *,
    manifest: PluginManifest,
    config: Any | None = None,
) -> PluginRunResult:
    output_dir = office_common.resolve_output_dir(context)
    pdf_path = output_dir / "Aoryn_PDF_Plugin_Report.pdf"
    report_path = output_dir / "Aoryn_PDF_Plugin_Report.md"
    actions = office_common.emit(context, "PDF 插件正在生成运行报告和追溯记录")

    lines = _pdf_lines(task)
    _write_simple_pdf(pdf_path, "Aoryn PDF Plugin Report", lines)
    office_common.copy_to_run_dir(pdf_path, context)

    markdown_path = office_common.write_text_artifact(
        context,
        report_path.name,
        _markdown_report(task=task, pdf_path=pdf_path),
    )
    office_common.open_artifacts(context, (pdf_path, markdown_path))

    answer = (
        "PDF 插件任务已完成：已生成 PDF 交付文件和 Markdown 追溯记录。\n\n"
        f"PDF：{pdf_path}\n"
        f"记录：{markdown_path}"
    )
    return PluginRunResult(
        completed=True,
        headline="PDF 插件已完成：生成运行报告",
        answer=answer,
        actions=actions,
        artifacts=[pdf_path.name, markdown_path.name],
    )


def _pdf_lines(task: str) -> list[str]:
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    return [
        "Aoryn PDF Plugin Report",
        f"Generated: {created}",
        "",
        "Task",
        _ascii_line(task) or "Create a short Aoryn operations report.",
        "",
        "Report scope",
        "- Plugin discovery through plugin.json.",
        "- Routing through plugin:pdf_report.",
        "- Stable file generation without external office software.",
        "- Traceable artifacts for review and handoff.",
        "",
        "Operational note",
        "Aoryn can expose focused plugins for professional software and file workflows.",
        "The core agent can still use screen control, while plugins provide reliable shortcuts.",
    ]


def _markdown_report(*, task: str, pdf_path: Path) -> str:
    return (
        "# PDF 报告插件记录\n\n"
        "## 任务\n\n"
        f"{task}\n\n"
        "## 产物\n\n"
        f"- PDF：`{pdf_path}`\n"
        "- Markdown：`Aoryn_PDF_Plugin_Report.md`\n\n"
        "## 运行价值\n\n"
        "- 插件无需依赖 Office 或 MATLAB，也能稳定生成可交付文件。\n"
        "- 任务通过插件发现和 `plugin:pdf_report` 路由执行。\n"
        "- 适合把通用桌面代理扩展为专业文件处理能力。\n"
    )


def _write_simple_pdf(path: Path, title: str, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text_commands = ["BT", "/F1 16 Tf", "72 760 Td", f"({_pdf_escape(title)}) Tj"]
    text_commands.extend(["/F1 10 Tf", "0 -28 Td"])
    for line in lines[1:]:
        text_commands.append(f"({_pdf_escape(_ascii_line(line))}) Tj")
        text_commands.append("0 -16 Td")
    text_commands.append("ET")
    stream = "\n".join(text_commands).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode("ascii"))
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(payload))
    return path


def _pdf_escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _ascii_line(value: str) -> str:
    text = " ".join(str(value or "").split())
    return text.encode("ascii", errors="ignore").decode("ascii").strip()
