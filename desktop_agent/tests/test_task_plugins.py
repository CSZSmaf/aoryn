import shutil
import tempfile
from pathlib import Path

from desktop_agent.config import AgentConfig
from desktop_agent.executor import MockExecutor
from desktop_agent.plugin_runtime import get_task_plugin, plugin_catalog
from desktop_agent.task_skills import TaskSkillRunner
from desktop_agent.task_plugins import office_common
from desktop_agent.task_plugins.coding_assistant import plugin as coding_plugin
from desktop_agent.task_plugins.matlab_plot import plugin as matlab_plugin


def test_matlab_plugin_is_discoverable(monkeypatch):
    monkeypatch.setattr(matlab_plugin, "_find_matlab_executable", lambda config=None: Path("C:/MATLAB/bin/matlab.exe"))

    items = plugin_catalog(config=AgentConfig())
    matlab = next(item for item in items if item["id"] == "matlab_plot")

    assert matlab["name"] == "MATLAB 绘图插件"
    assert matlab["status"]["state"] == "ready"
    assert "MATLAB" in matlab["demo_task"]


def test_office_plugins_are_discoverable(monkeypatch):
    monkeypatch.setattr(office_common, "find_office_executable", lambda app, config=None: None)

    items = plugin_catalog(config=AgentConfig())
    ids = {item["id"] for item in items}

    assert {"excel_report", "powerpoint_deck", "word_report"}.issubset(ids)
    assert next(item for item in items if item["id"] == "excel_report")["status"]["state"] == "available"


def test_coding_plugin_is_discoverable():
    items = plugin_catalog(config=AgentConfig())
    coding = next(item for item in items if item["id"] == "coding_assistant")

    assert coding["name"] == "Coding Assistant Plugin"
    assert coding["status"]["state"] == "available"
    assert "coding plugin" in coding["demo_task"].lower()


def test_task_runner_routes_matlab_plot_to_plugin(monkeypatch):
    monkeypatch.setattr(matlab_plugin, "_find_matlab_executable", lambda config=None: Path("C:/MATLAB/bin/matlab.exe"))

    runner = TaskSkillRunner(AgentConfig())

    assert runner.match("用 MATLAB 绘制 y=sin(x) 曲线，保存图像") == "plugin:matlab_plot"


def test_task_runner_routes_office_plugins(monkeypatch):
    monkeypatch.setattr(office_common, "find_office_executable", lambda app, config=None: None)

    runner = TaskSkillRunner(AgentConfig())

    assert runner.match("用 Excel 插件生成销售报表和图表") == "plugin:excel_report"
    assert runner.match("用 PowerPoint 插件生成 Aoryn 五分钟演示稿") == "plugin:powerpoint_deck"
    assert runner.match("用 Word 插件生成 Aoryn 插件能力报告") == "plugin:word_report"


def test_task_runner_routes_coding_plugin():
    runner = TaskSkillRunner(AgentConfig())

    assert runner.match("Use the coding plugin to create a Python text statistics utility") == "plugin:coding_assistant"
    assert runner.match("write code for a todo list and run tests") == "plugin:coding_assistant"


def test_coding_plugin_matcher_stays_narrow_for_plain_search():
    assert not coding_plugin.match_task("search the web for programming tutorials", manifest=None)  # type: ignore[arg-type]


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


def test_excel_plugin_generates_fallback_artifacts_without_excel(monkeypatch):
    temp_root = Path(tempfile.mkdtemp(prefix="aoryn_excel_plugin_test_"))
    try:
        monkeypatch.setattr(office_common, "find_office_executable", lambda app, config=None: None)
        config = AgentConfig()
        executor = MockExecutor(config)
        run_dir = temp_root / "run"
        output_dir = temp_root / "out"

        result = TaskSkillRunner(config).run(
            "plugin:excel_report",
            "用 Excel 插件生成销售数据报表和趋势图",
            executor=executor,
            run_dir=run_dir,
            output_dir=output_dir,
            open_artifacts=False,
        )

        assert result.handled and result.completed
        assert (output_dir / "Aoryn_Excel插件销售分析.xlsx").exists()
        assert (output_dir / "Aoryn_Excel插件销售趋势.png").exists()
        assert (output_dir / "Aoryn_Excel插件报告.md").exists()
        assert get_task_plugin("excel_report") is not None
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_powerpoint_plugin_generates_html_without_powerpoint(monkeypatch):
    temp_root = Path(tempfile.mkdtemp(prefix="aoryn_ppt_plugin_test_"))
    try:
        monkeypatch.setattr(office_common, "find_office_executable", lambda app, config=None: None)
        config = AgentConfig()
        executor = MockExecutor(config)
        run_dir = temp_root / "run"
        output_dir = temp_root / "out"

        result = TaskSkillRunner(config).run(
            "plugin:powerpoint_deck",
            "用 PowerPoint 插件生成 Aoryn 五分钟演示稿",
            executor=executor,
            run_dir=run_dir,
            output_dir=output_dir,
            open_artifacts=False,
        )

        assert result.handled and result.completed
        assert (output_dir / "Aoryn_PowerPoint插件演示稿.pptx").exists()
        assert (output_dir / "Aoryn_PowerPoint插件演示稿.html").exists()
        assert (output_dir / "Aoryn_PowerPoint插件报告.md").exists()
        assert get_task_plugin("powerpoint_deck") is not None
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_word_plugin_generates_docx(monkeypatch):
    temp_root = Path(tempfile.mkdtemp(prefix="aoryn_word_plugin_test_"))
    try:
        monkeypatch.setattr(office_common, "find_office_executable", lambda app, config=None: None)
        config = AgentConfig()
        executor = MockExecutor(config)
        run_dir = temp_root / "run"
        output_dir = temp_root / "out"

        result = TaskSkillRunner(config).run(
            "plugin:word_report",
            "用 Word 插件生成 Aoryn 插件能力报告",
            executor=executor,
            run_dir=run_dir,
            output_dir=output_dir,
            open_artifacts=False,
        )

        assert result.handled and result.completed
        assert (output_dir / "Aoryn_Word插件能力报告.docx").exists()
        assert (output_dir / "Aoryn_Word插件报告.md").exists()
        assert get_task_plugin("word_report") is not None
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_coding_plugin_generates_project_and_verification_artifacts():
    temp_root = Path(tempfile.mkdtemp(prefix="aoryn_coding_plugin_test_"))
    try:
        config = AgentConfig()
        executor = MockExecutor(config)
        run_dir = temp_root / "run"
        output_dir = temp_root / "out"

        result = TaskSkillRunner(config).run(
            "plugin:coding_assistant",
            "Use the coding plugin to create a Python text statistics utility and run tests",
            executor=executor,
            run_dir=run_dir,
            output_dir=output_dir,
            open_artifacts=False,
        )

        assert result.handled and result.completed
        assert (output_dir / "Aoryn_Coding_Plugin_Project.zip").exists()
        assert (output_dir / "Aoryn_Coding_Plugin.patch").exists()
        assert (output_dir / "Aoryn_Coding_Plugin_Report.md").exists()
        verification = (output_dir / "Aoryn_Coding_Plugin_Verification.txt").read_text(encoding="utf-8")
        assert "Result: PASS" in verification
        assert (output_dir / "Aoryn_Coding_Plugin_Project" / "src" / "aoryn_text_stats" / "stats.py").exists()
        assert get_task_plugin("coding_assistant") is not None
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
