import shutil
import tempfile
from pathlib import Path

from desktop_agent.config import AgentConfig
from desktop_agent.executor import MockExecutor
from desktop_agent.plugin_runtime import get_task_plugin, plugin_catalog
from desktop_agent.task_skills import TaskSkillRunner
from desktop_agent.task_plugins.matlab_plot import plugin as matlab_plugin


def test_matlab_plugin_is_discoverable(monkeypatch):
    monkeypatch.setattr(matlab_plugin, "_find_matlab_executable", lambda config=None: Path("C:/MATLAB/bin/matlab.exe"))

    items = plugin_catalog(config=AgentConfig())
    matlab = next(item for item in items if item["id"] == "matlab_plot")

    assert matlab["name"] == "MATLAB 绘图插件"
    assert matlab["status"]["state"] == "ready"
    assert "MATLAB" in matlab["demo_task"]


def test_task_runner_routes_matlab_plot_to_plugin(monkeypatch):
    monkeypatch.setattr(matlab_plugin, "_find_matlab_executable", lambda config=None: Path("C:/MATLAB/bin/matlab.exe"))

    runner = TaskSkillRunner(AgentConfig())

    assert runner.match("用 MATLAB 绘制 y=sin(x) 曲线，保存图像") == "plugin:matlab_plot"


def test_matlab_plugin_generates_artifacts_without_real_matlab(monkeypatch):
    temp_root = Path(tempfile.mkdtemp(prefix="aoryn_plugin_test_"))
    try:
        config = AgentConfig()
        executor = MockExecutor(config)
        run_dir = temp_root / "run"
        output_dir = temp_root / "out"

        monkeypatch.setattr(matlab_plugin, "_find_matlab_executable", lambda config=None: Path("C:/MATLAB/bin/matlab.exe"))

        def fake_run(executable, script_path, *, cwd, timeout):
            cwd = Path(cwd)
            (cwd / "aoryn_matlab_plot.png").write_bytes(b"fake-png")
            (cwd / "aoryn_matlab_result.txt").write_text("MATLAB plugin completed successfully.", encoding="utf-8")
            return True, "ok", ""

        monkeypatch.setattr(matlab_plugin, "_run_matlab_batch", fake_run)

        result = TaskSkillRunner(config).run(
            "plugin:matlab_plot",
            "用 MATLAB 绘制 y=sin(x) 曲线，保存图像并写出结果说明",
            executor=executor,
            run_dir=run_dir,
            output_dir=output_dir,
            open_artifacts=False,
        )

        assert result.handled and result.completed
        assert "MATLAB 插件任务已完成" in result.answer
        assert (output_dir / "MATLAB插件_sin曲线.png").exists()
        assert (output_dir / "MATLAB插件_aoryn_matlab_plot.m").exists()
        assert (output_dir / "MATLAB插件演示报告.md").exists()
        assert get_task_plugin("matlab_plot") is not None
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
