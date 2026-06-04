from __future__ import annotations

from pathlib import Path
from typing import Any

from desktop_agent.plugin_runtime import PluginManifest, PluginRunResult
from desktop_agent.task_plugins import office_common


_PPT_TERMS = ("powerpoint", "ppt", "pptx", "幻灯片", "演示文稿", "演示稿")
_WORK_TERMS = ("插件", "aoryn", "演示", "汇报", "展示", "presentation", "deck", "demo")

_SLIDES: list[tuple[str, list[str]]] = [
    ("Aoryn 桌面智能代理系统", ["目标：让代理像人一样观察屏幕、判断下一步、操作软件。", "展示重点：稳定示例、插件扩展、可追溯证据。"]),
    ("核心闭环", ["截图与视觉理解", "大模型/规则脑进行决策", "鼠标键盘和软件插件执行动作"]),
    ("已稳定的演示任务", ["计算器完成 1+1", "浏览器阅读多个网页并写 Typora 报告", "画图工具逐笔绘制图形", "MATLAB 插件生成函数曲线"]),
    ("插件机制", ["每个插件声明触发词、能力、状态和演示任务。", "前端自动展示插件目录。", "任务路由可以把专业软件任务交给对应插件。"]),
    ("后续扩展", ["为 QQ、MATLAB、Office、CAD 等软件添加专用插件。", "把通用视觉代理与软件专用 API/脚本结合。", "让演示更稳，同时保留可解释的执行证据。"]),
]


def match_task(task: str, *, manifest: PluginManifest, config: Any | None = None) -> bool:
    text = str(task or "")
    lowered = text.lower()
    has_ppt = any(term.lower() in lowered for term in _PPT_TERMS)
    has_work = any(term in text or term.lower() in lowered for term in _WORK_TERMS)
    return has_ppt and has_work


def status(*, manifest: PluginManifest, config: Any | None = None) -> dict[str, Any]:
    return office_common.office_status("powerpoint", config=config, file_label="an HTML slide deck")


def run_task(
    task: str,
    context: Any,
    *,
    manifest: PluginManifest,
    config: Any | None = None,
) -> PluginRunResult:
    output_dir = office_common.resolve_output_dir(context)
    pptx_path = output_dir / "Aoryn_PowerPoint插件演示稿.pptx"
    html_path = output_dir / "Aoryn_PowerPoint插件演示稿.html"
    actions = office_common.emit(context, "PowerPoint 插件正在生成 Aoryn 演示稿")

    executable = office_common.find_office_executable("powerpoint", config) if _prefers_real_office(task) else None
    mode = "HTML 演示稿降级输出"
    pptx_error: str | None = None
    pptx_created = False
    if executable is not None:
        try:
            _write_with_powerpoint_com(pptx_path)
            pptx_created = True
            mode = f"PowerPoint COM 自动化：{executable}"
        except Exception as exc:
            pptx_error = str(exc)
    if not pptx_created:
        office_common.write_basic_pptx(pptx_path, "Aoryn PowerPoint 插件演示稿", _SLIDES)
        pptx_created = True
        mode = "标准 PPTX 文件生成" if pptx_error is None else "标准 PPTX 文件生成（COM 不可用时降级）"
    office_common.write_html_deck(html_path, "Aoryn PowerPoint 插件演示稿", _SLIDES)

    for path in (pptx_path if pptx_created else None, html_path):
        if path is not None:
            office_common.copy_to_run_dir(path, context)
    report_path = office_common.write_text_artifact(
        context,
        "Aoryn_PowerPoint插件报告.md",
        _report(task=task, mode=mode, pptx=pptx_path if pptx_created else None, html=html_path, error=pptx_error),
    )
    office_common.open_artifacts(context, (pptx_path if pptx_created else html_path, report_path))

    artifacts = ([pptx_path.name] if pptx_created else []) + [html_path.name, report_path.name]
    answer = (
        "✅ PowerPoint 插件任务已完成：已生成 Aoryn 演示稿和插件报告。\n\n"
        f"执行方式：{mode}\n"
        f"PPTX：{pptx_path}\n"
        f"HTML：{html_path}\n"
        f"报告：{report_path}"
    )
    return PluginRunResult(
        completed=True,
        headline="PowerPoint 插件已完成：生成 Aoryn 演示稿",
        answer=answer,
        actions=actions,
        artifacts=artifacts,
    )


def _write_with_powerpoint_com(pptx_path: Path) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = None
    presentation = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        app.Visible = True
        presentation = app.Presentations.Add()
        for index, (title, bullets) in enumerate(_SLIDES, start=1):
            slide = presentation.Slides.Add(index, 2)
            _set_text(slide.Shapes.Title, title)
            body = "\r".join(bullets)
            try:
                _set_text(slide.Shapes.Placeholders(2), body)
            except Exception:
                box = slide.Shapes.AddTextbox(1, 80, 145, 820, 320)
                _set_text(box, body)
        presentation.SaveAs(str(pptx_path), 24)
        presentation.Close()
        presentation = None
    finally:
        if presentation is not None:
            presentation.Close()
        if app is not None:
            app.Quit()
        pythoncom.CoUninitialize()


def _set_text(shape: Any, text: str) -> None:
    shape.TextFrame.TextRange.Text = text


def _prefers_real_office(task: str) -> bool:
    text = str(task or "").lower()
    terms = (
        "com",
        "real powerpoint",
        "open powerpoint",
        "visible powerpoint",
        "office automation",
        "\u6253\u5f00",
        "\u754c\u9762",
        "\u64cd\u7eb5",
        "\u771f\u5b9e",
        "\u81ea\u52a8\u5316",
    )
    return any(term in text for term in terms)


def _report(*, task: str, mode: str, pptx: Path | None, html: Path, error: str | None) -> str:
    warning = f"\n\n> PowerPoint COM 失败后已降级为 HTML：{error}" if error else ""
    return (
        "# PowerPoint 插件演示报告\n\n"
        f"## 任务\n\n{task}\n\n"
        "## 产物\n\n"
        f"- PPTX：{pptx or '(未生成)'}\n"
        f"- HTML 演示稿：{html}\n"
        f"- 执行方式：{mode}\n\n"
        "## 演示结构\n\n"
        + "\n".join(f"- {title}" for title, _ in _SLIDES)
        + f"{warning}\n"
    )
