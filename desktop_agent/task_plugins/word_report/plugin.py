from __future__ import annotations

from pathlib import Path
from typing import Any

from desktop_agent.plugin_runtime import PluginManifest, PluginRunResult
from desktop_agent.task_plugins import office_common


_WORD_TERMS = ("word 插件", "word plugin", "docx 插件", "插件报告", "aoryn 报告", "Aoryn 报告")

_SECTIONS: list[tuple[str, list[str]]] = [
    ("插件架构", ["插件通过 plugin.json 声明身份、触发词、能力和默认任务。", "后端自动发现插件并通过 plugin:ID 路由任务。", "前端从 task_plugins 元数据渲染插件卡片。"]),
    ("当前插件", ["MATLAB 绘图插件：调用 MATLAB 批处理生成曲线图。", "Excel 报表插件：生成工作簿、趋势图和分析报告。", "PowerPoint 文稿插件：生成汇报文稿和 HTML 预览。", "Word 报告插件：生成 DOCX 汇报文档。"]),
    ("运行价值", ["系统具备按软件扩展的接口。", "插件能把专业软件的稳定 API/COM 能力和通用视觉代理结合。", "每个插件都会留下产物和运行记录，方便现场追溯。"]),
    ("后续计划", ["为 QQ 群聊、CAD、MATLAB 更多函数、浏览器站点定制插件。", "补充插件安装、启停和权限配置界面。", "增加插件目录和插件运行日志。"]),
]


def match_task(task: str, *, manifest: PluginManifest, config: Any | None = None) -> bool:
    lowered = str(task or "").lower()
    return any(term.lower() in lowered for term in _WORD_TERMS)


def status(*, manifest: PluginManifest, config: Any | None = None) -> dict[str, Any]:
    return office_common.office_status("word", config=config, file_label="a .docx report")


def run_task(
    task: str,
    context: Any,
    *,
    manifest: PluginManifest,
    config: Any | None = None,
) -> PluginRunResult:
    output_dir = office_common.resolve_output_dir(context)
    docx_path = output_dir / "Aoryn_Word插件能力报告.docx"
    actions = office_common.emit(context, "Word 插件正在生成 DOCX 插件运行报告")

    office_common.write_basic_docx(docx_path, "Aoryn 插件运行报告", _SECTIONS)
    office_common.copy_to_run_dir(docx_path, context)
    report_path = office_common.write_text_artifact(
        context,
        "Aoryn_Word插件报告.md",
        _report(task=task, docx=docx_path, word=office_common.find_office_executable("word", config)),
    )
    office_common.open_artifacts(context, (docx_path, report_path))

    answer = (
        "✅ Word 插件任务已完成：已生成 DOCX 插件运行报告和 Markdown 记录。\n\n"
        f"DOCX：{docx_path}\n"
        f"报告：{report_path}"
    )
    return PluginRunResult(
        completed=True,
        headline="Word 插件已完成：生成 Aoryn 插件运行报告",
        answer=answer,
        actions=actions,
        artifacts=[docx_path.name, report_path.name],
    )


def _report(*, task: str, docx: Path, word: Path | None) -> str:
    return (
        "# Word 插件报告\n\n"
        f"## 任务\n\n{task}\n\n"
        "## 产物\n\n"
        f"- DOCX：{docx}\n"
        f"- Word：{word or '未发现 Word，可用兼容软件打开 DOCX'}\n\n"
        "## 内容\n\n"
        + "\n".join(f"- {heading}" for heading, _ in _SECTIONS)
        + "\n"
    )
