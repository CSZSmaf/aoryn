from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from desktop_agent.actions import Action
from desktop_agent.plugin_runtime import PluginManifest, PluginRunResult


_MATLAB_TERMS = ("matlab", "MATLAB")
_PLOT_TERMS = ("绘图", "画图", "函数", "曲线", "plot", "draw", "figure")
_MATRIX_TERMS = ("矩阵", "特征值", "matrix", "eigen")


def match_task(task: str, *, manifest: PluginManifest, config: Any | None = None) -> bool:
    text = str(task or "")
    lowered = text.lower()
    has_matlab = any(term.lower() in lowered for term in _MATLAB_TERMS)
    has_work = any(term in text or term.lower() in lowered for term in (*_PLOT_TERMS, *_MATRIX_TERMS))
    return has_matlab and has_work


def status(*, manifest: PluginManifest, config: Any | None = None) -> dict[str, Any]:
    executable = _find_matlab_executable(config)
    if executable is None:
        return {
            "state": "needs_app",
            "label": "MATLAB not found",
            "detail": "Install MATLAB or set app_launch_map.matlab to matlab.exe.",
        }
    return {
        "state": "ready",
        "label": "Ready",
        "detail": str(executable),
    }


def run_task(
    task: str,
    context: Any,
    *,
    manifest: PluginManifest,
    config: Any | None = None,
) -> PluginRunResult:
    executable = _find_matlab_executable(config)
    if executable is None:
        return PluginRunResult(
            completed=False,
            headline="MATLAB 插件未就绪：未找到 MATLAB",
            answer=(
                "⚠️ 已识别到 MATLAB 插件任务，但当前系统没有找到 matlab.exe。\n\n"
                "可在配置中的 app_launch_map.matlab 指向 MATLAB 可执行文件，"
                "或安装 MATLAB 后重新运行。"
            ),
            error="matlab executable not found",
        )

    work_dir = Path(tempfile.mkdtemp(prefix="aoryn_matlab_"))
    run_dir = getattr(context, "run_dir", None)
    output_dir = getattr(context, "output_dir", None) or run_dir or Path.cwd()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if run_dir is not None:
        Path(run_dir).mkdir(parents=True, exist_ok=True)

    spec = _plot_spec(task)
    script_path = work_dir / "aoryn_matlab_plot.m"
    png_path = work_dir / "aoryn_matlab_plot.png"
    result_path = work_dir / "aoryn_matlab_result.txt"
    script_path.write_text(_matlab_script(spec, png_path, result_path), encoding="utf-8")

    actions = [
        Action.from_dict({"type": "wait", "seconds": 0.2}),
    ]
    _emit(context, actions, f"MATLAB 插件已生成脚本，准备调用 {Path(executable).name} 绘图")

    completed, stdout, stderr = _run_matlab_batch(executable, script_path, cwd=work_dir, timeout=240)
    if not completed:
        return PluginRunResult(
            completed=False,
            headline="MATLAB 插件执行失败",
            answer=(
                "⚠️ MATLAB 插件已启动，但脚本没有成功完成。\n\n"
                f"MATLAB：{executable}\n"
                f"脚本：{script_path}\n"
                f"错误：{(stderr or stdout or '无输出')[:1200]}"
            ),
            actions=actions,
            artifacts=[],
            error=(stderr or stdout or "matlab batch failed")[:1000],
        )

    artifacts: list[str] = []
    copied_script = _copy_artifact(script_path, output_dir, "MATLAB插件_aoryn_matlab_plot.m", run_dir)
    copied_png = _copy_artifact(png_path, output_dir, "MATLAB插件_sin曲线.png", run_dir)
    copied_txt = _copy_artifact(result_path, output_dir, "MATLAB插件_结果说明.txt", run_dir)
    for path in (copied_png, copied_txt, copied_script):
        if path is not None:
            artifacts.append(path.name)

    report = _markdown_report(task=task, spec=spec, executable=executable, png=copied_png, txt=copied_txt)
    report_path = _write_report(context, "MATLAB插件演示报告.md", report)
    if report_path is not None:
        artifacts.append(report_path.name)

    if bool(getattr(context, "open_artifacts", False)):
        opener = getattr(context, "open_path", None)
        for path in (copied_png, report_path):
            if path is not None and callable(opener):
                try:
                    opener(path)
                except Exception:
                    pass

    answer = (
        "✅ MATLAB 插件任务已完成：插件发现 MATLAB 后生成 `.m` 脚本，调用 MATLAB 批处理执行，"
        "并保存曲线图、结果说明和 Markdown 报告。\n\n"
        f"函数：{spec['label']}\n"
        f"MATLAB：{executable}\n"
        f"图像：{copied_png}\n"
        f"报告：{report_path}"
    )
    return PluginRunResult(
        completed=True,
        headline=f"MATLAB 插件已完成：生成 {spec['label']} 曲线图",
        answer=answer,
        actions=actions,
        artifacts=artifacts,
    )


def _emit(context: Any, actions: list[Action], headline: str) -> None:
    execute = getattr(context, "execute", None)
    if callable(execute):
        execute(actions, headline)


def _find_matlab_executable(config: Any | None) -> Path | None:
    configured = ""
    app_launch_map = getattr(config, "app_launch_map", None)
    if isinstance(app_launch_map, dict):
        configured = str(app_launch_map.get("matlab") or "").strip()
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    which = shutil.which("matlab") or shutil.which("matlab.exe")
    if which:
        candidates.append(which)
    matlab_root = os.environ.get("MATLABROOT")
    if matlab_root:
        candidates.append(str(Path(matlab_root) / "bin" / "matlab.exe"))
    for base in (
        Path("C:/Program Files/MATLAB"),
        Path("C:/Program Files (x86)/MATLAB"),
        Path("D:/Program Files/MATLAB"),
        Path("D:/MATLAB"),
    ):
        if not base.exists():
            continue
        for candidate in sorted(base.glob("R*/bin/matlab.exe"), reverse=True):
            candidates.append(str(candidate))
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.strip().strip('"')
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved = shutil.which(normalized) or normalized
        path = Path(resolved)
        if path.is_file():
            return path
    return None


def _plot_spec(task: str) -> dict[str, str]:
    lowered = str(task or "").lower()
    if "cos" in lowered or "余弦" in task:
        return {"expr": "cos(x)", "label": "y = cos(x)", "title": "Aoryn MATLAB Plugin: cos(x)"}
    if "x^2" in lowered or "x2" in lowered or "平方" in task:
        return {"expr": "x.^2", "label": "y = x^2", "title": "Aoryn MATLAB Plugin: x^2"}
    return {"expr": "sin(x)", "label": "y = sin(x)", "title": "Aoryn MATLAB Plugin: sin(x)"}


def _matlab_script(spec: dict[str, str], png_path: Path, result_path: Path) -> str:
    expr = spec["expr"]
    label = spec["label"]
    title = spec["title"].replace("'", "''")
    png = _matlab_path(png_path)
    result = _matlab_path(result_path)
    return f"""
x = linspace(0, 2*pi, 600);
y = {expr};
fig = figure('Visible', 'off', 'Color', 'white', 'Position', [120 120 960 540]);
plot(x, y, 'LineWidth', 2.5, 'Color', [0.0 0.35 0.75]);
grid on;
title('{title}', 'Interpreter', 'none');
xlabel('x');
ylabel('{label}');
exportgraphics(fig, '{png}', 'Resolution', 160);
fid = fopen('{result}', 'w', 'n', 'UTF-8');
fprintf(fid, 'MATLAB plugin completed successfully.\\n');
fprintf(fid, 'Function: {label}\\n');
fprintf(fid, 'Samples: %d\\n', numel(x));
fprintf(fid, 'Y min: %.6f\\n', min(y));
fprintf(fid, 'Y max: %.6f\\n', max(y));
fclose(fid);
close(fig);
""".strip()


def _run_matlab_batch(executable: Path, script_path: Path, *, cwd: Path, timeout: int) -> tuple[bool, str, str]:
    command = [str(executable), "-batch", f"run('{_matlab_path(script_path)}')"]
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return False, exc.stdout or "", exc.stderr or "MATLAB execution timed out."
    except Exception as exc:
        return False, "", str(exc)
    return result.returncode == 0, result.stdout or "", result.stderr or ""


def _copy_artifact(source: Path, output_dir: Path, filename: str, run_dir: Path | None) -> Path | None:
    if not source.exists():
        return None
    target = output_dir / filename
    shutil.copy2(source, target)
    if run_dir is not None and Path(run_dir) != output_dir:
        try:
            shutil.copy2(target, Path(run_dir) / filename)
        except Exception:
            pass
    return target


def _write_report(context: Any, filename: str, content: str) -> Path | None:
    writer = getattr(context, "write_text_file", None)
    if callable(writer):
        try:
            return writer(filename, content)
        except Exception:
            return None
    return None


def _markdown_report(
    *,
    task: str,
    spec: dict[str, str],
    executable: Path,
    png: Path | None,
    txt: Path | None,
) -> str:
    return (
        "# MATLAB 插件报告\n\n"
        "## 任务\n\n"
        f"{task}\n\n"
        "## 插件执行\n\n"
        "- 插件：matlab_plot\n"
        f"- MATLAB：{executable}\n"
        f"- 绘制函数：{spec['label']}\n"
        "- 执行方式：生成 MATLAB `.m` 脚本，使用 MATLAB `-batch` 执行并保存图像。\n\n"
        "## 产物\n\n"
        f"- 曲线图：{png or '(未生成)'}\n"
        f"- 结果说明：{txt or '(未生成)'}\n"
    )


def _matlab_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")
