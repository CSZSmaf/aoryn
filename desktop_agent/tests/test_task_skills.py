import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest

from desktop_agent.config import AgentConfig
from desktop_agent.executor import MockExecutor


@pytest.fixture()
def workdir():
    # Use the OS temp dir directly to avoid the project's locked pytest_temp
    # base path on Windows; tolerate teardown locks with ignore_errors.
    path = Path(tempfile.mkdtemp(prefix="aoryn_skill_"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
from desktop_agent.task_skills import (
    TaskSkillRunner,
    _extract_timer_duration,
    _parse_model_strokes,
    _parse_visual_ocr_response,
    build_beijing_plan_text,
    build_beijing_travel_summary,
    compose_poem,
    evaluate_expression,
    extract_arithmetic_expression,
    extract_qq_group_message,
    format_number,
    has_enough_beijing_travel_evidence,
    write_beijing_docx,
)
from desktop_agent.web_research import PageReading, classify_page, extract_brand_mentions, extract_prices


@pytest.fixture()
def runner() -> TaskSkillRunner:
    return TaskSkillRunner(AgentConfig())


# --- matching --------------------------------------------------------------


@pytest.mark.parametrize(
    "task, expected",
    [
        ("打开计算器计算1+1", "calculator"),
        ("用计算器算 (2+3)*4", "calculator"),
        ("open calculator and calculate 1+1", "calculator"),
        ("打开记事本写一首诗", "notepad_poem"),
        ("用记事本写诗", "notepad_poem"),
        ("用画图工具画一只猫", "paint_drawing"),
        ("open paint and draw a cat", "paint_drawing"),
        ("用画图工具画一个房子", "paint_drawing"),
        ("用计时器定一个1分钟闹钟", "clock_timer_alarm"),
        ("open clock and set a 30 second timer", "clock_timer_alarm"),
        ("上购物网站搜索男性裤子并分析性价比", "shopping_pants"),
        ("shop for high-value men's pants on amazon", "shopping_pants"),
        ("打开浏览器搜索北京旅游攻略，阅读多个网页后总结，并把总结内容写在记事本上", "travel_notepad"),
        ("上网搜索北京旅游景点并给出3天旅游规划，用word写出来", "travel_word"),
        ("打开QQ在群聊“项目演示群”发送消息“今天的演示已准备好”", "qq_group_message"),
        # negatives
        ("open notepad", None),
        ("open calculator", None),
        ("search for OpenAI", None),
        ("wait 3 天", None),
        ("打开记事本输入 hello", None),
        ("北京今天天气怎么样", None),
    ],
)
def test_match(runner: TaskSkillRunner, task: str, expected):
    assert runner.match(task) == expected


# --- arithmetic ------------------------------------------------------------


@pytest.mark.parametrize(
    "expr, value",
    [
        ("1+1", 2),
        ("(2+3)*4", 20),
        ("12/4", 3),
        ("2.5*2", 5),
        ("10-3-2", 5),
        ("-3+5", 2),
    ],
)
def test_evaluate_expression(expr: str, value: float):
    assert evaluate_expression(expr) == value


def test_extract_arithmetic_handles_chinese_operators():
    assert extract_arithmetic_expression("打开计算器计算 三 加 二") is None  # words only, no digits
    assert extract_arithmetic_expression("计算器算 2 乘以 3") == "2*3"
    assert extract_arithmetic_expression("3天行程") is None


def test_division_by_zero_raises():
    with pytest.raises(ValueError):
        evaluate_expression("5/0")


def test_format_number():
    assert format_number(2.0) == "2"
    assert format_number(2.5) == "2.5"


# --- poem ------------------------------------------------------------------


def test_compose_poem_generic_is_deterministic():
    title_a, body_a = compose_poem("打开记事本写一首诗")
    title_b, body_b = compose_poem("打开记事本写一首诗")
    assert title_a == title_b and body_a == body_b
    assert body_a.count("\n") == 3  # a four-line verse


def test_compose_poem_theme():
    title, body = compose_poem("写一首关于春的诗")
    assert "春" in title
    assert body.startswith("春")


# --- web research helpers (honest, page-grounded) --------------------------


def test_classify_page_detects_login_verification_and_ok():
    assert classify_page(None).status == "error"
    assert classify_page({"url": "https://passport.jd.com/new/login.aspx", "title": "登录", "text": "请登录"}).status == "login"
    assert classify_page({"url": "https://www.baidu.com/s", "title": "百度安全验证", "text": "请完成验证"}).status == "verification"
    assert classify_page({"url": "x", "title": "x", "text": "短"}).status == "empty"
    search = classify_page(
        {
            "url": "https://cn.bing.com/search?q=北京旅游攻略&mkt=zh-CN",
            "title": "北京旅游攻略 - 搜索",
            "text": "网页 图片 视频 更多 约 65,200 个结果 北京旅游攻略 " * 20,
        }
    )
    assert search.status == "search_results"
    assert not search.usable
    redirected_search = classify_page(
        {
            "url": "https://www.bing.com/search?q=北京旅游攻略&mkt=zh-CN",
            "title": "北京旅游攻略 - 搜索",
            "text": "网页 图片 视频 更多 约 65,200 个结果 北京旅游攻略 " * 20,
        }
    )
    assert redirected_search.status == "search_results"
    assert not redirected_search.usable
    ok = classify_page({"url": "https://search.jd.com", "title": "男士裤子", "text": "李宁速干裤 ¥159 海澜之家 " * 20})
    assert ok.status == "ok" and ok.usable


def test_extract_prices_and_brands_from_real_text():
    text = "李宁 速干裤 ¥159 元 海澜之家 商务裤 ￥199 优衣库弹力裤 99元"
    prices = extract_prices(text)
    assert "¥159" in prices and "¥199" in prices and "¥99" in prices
    brands = extract_brand_mentions(text, ("李宁", "海澜之家", "优衣库", "Lee"))
    assert "李宁" in brands and "海澜之家" in brands and "优衣库" in brands
    assert "Lee" not in brands  # not present in the text, must not be invented


# --- docx ------------------------------------------------------------------


def test_write_beijing_docx(workdir):
    path = write_beijing_docx(workdir / "plan.docx")
    assert path.exists()
    assert zipfile.is_zipfile(path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert "[Content_Types].xml" in names
        assert "word/document.xml" in names
        document = archive.read("word/document.xml").decode("utf-8")
        assert "北京" in document
        assert "故宫" in document


def test_build_beijing_plan_text_has_three_days():
    text = build_beijing_plan_text()
    assert "第一天" in text and "第二天" in text and "第三天" in text


def test_build_beijing_travel_summary_records_page_readings():
    readings = [
        PageReading("ok", "https://example.test/a", "北京攻略A", "故宫 天安门 景山 预约 地铁 " * 20, "ok"),
        PageReading("empty", "https://example.test/b", "空页面", "", "页面为空"),
    ]

    summary = build_beijing_travel_summary(readings)

    assert "北京旅游攻略总结" in summary
    assert "北京攻略A" in summary
    assert "故宫" in summary
    assert "页面为空" in summary
    assert not has_enough_beijing_travel_evidence(readings)
    assert "未生成最终攻略" in summary
    assert "二、综合建议" not in summary


def test_build_beijing_travel_summary_requires_multiple_readable_pages():
    readings = [
        PageReading("ok", "https://example.test/a", "北京攻略A", "故宫 天安门 景山 预约 地铁 " * 20, "ok"),
        PageReading("ok", "https://example.test/b", "北京攻略B", "长城 颐和园 胡同 烤鸭 " * 20, "ok"),
    ]

    summary = build_beijing_travel_summary(readings)

    assert has_enough_beijing_travel_evidence(readings)
    assert "二、综合建议" in summary
    assert "本次已成功读取 2 个网页" in summary


def test_parse_visual_ocr_response_accepts_json_fence():
    raw = '```json\n{"title":"Visible Beijing Guide","visible_text":"Forbidden City Great Wall Hutong"}\n```'

    title, text = _parse_visual_ocr_response(raw, default_title="fallback")

    assert title == "Visible Beijing Guide"
    assert "Forbidden City" in text


def test_parse_visual_ocr_response_accepts_jsonish_text():
    raw = '```json\n{"title":"Visible Beijing Guide","visible_text":"Forbidden City\\nGreat Wall"}\n```'

    title, text = _parse_visual_ocr_response(raw, default_title="fallback")

    assert title == "Visible Beijing Guide"
    assert "Great Wall" in text


def test_parse_visual_ocr_response_accepts_truncated_visible_text():
    raw = '```json\n{"title":"Visible Beijing Guide","visible_text":"Forbidden City\\nGreat Wall'

    title, text = _parse_visual_ocr_response(raw, default_title="fallback")

    assert title == "Visible Beijing Guide"
    assert text == "Forbidden City\nGreat Wall"


def test_extract_qq_group_message_accepts_quoted_instruction():
    request = extract_qq_group_message("打开QQ在群聊“项目演示群”发送消息“今天的演示已准备好”")

    assert request.group_name == "项目演示群"
    assert request.message == "今天的演示已准备好"


def test_extract_qq_group_message_accepts_labels():
    request = extract_qq_group_message("QQ 群名：课程实训群，消息：演示开始")

    assert request.group_name == "课程实训群"
    assert request.message == "演示开始"


@pytest.mark.parametrize(
    "task, seconds, label",
    [
        ("用计时器定一个1分钟闹钟", 60, "1分钟"),
        ("open clock and set a 30 second timer", 30, "30秒"),
        ("设置两分钟计时器", 120, "2分钟"),
        ("定个闹钟", 60, "1分钟"),
    ],
)
def test_extract_timer_duration(task: str, seconds: int, label: str):
    assert _extract_timer_duration(task) == (seconds, label)


# --- end-to-end via MockExecutor ------------------------------------------


def test_run_calculator_executes_and_answers(runner: TaskSkillRunner):
    executor = MockExecutor(AgentConfig())
    result = runner.run("calculator", "打开计算器计算1+1", executor=executor)
    assert result.handled and result.completed
    assert "1+1" in [a.get("text") for a in executor.executed if a.get("type") == "type"][0]
    assert "= 2" in result.answer
    assert result.headline


def test_run_notepad_poem_types_into_notepad(runner: TaskSkillRunner):
    # No output dir -> falls back to driving Notepad via the executor.
    executor = MockExecutor(AgentConfig())
    result = runner.run("notepad_poem", "打开记事本写一首诗", executor=executor)
    assert result.handled and result.completed
    assert executor.state.active_app == "notepad"
    assert "《" in result.answer


def test_run_notepad_poem_writes_text_file(workdir, runner: TaskSkillRunner):
    # With an output dir -> reliable file-based path (writes .txt, opens Notepad).
    executor = MockExecutor(AgentConfig())
    out = workdir / "out"
    result = runner.run(
        "notepad_poem",
        "打开记事本写一首诗",
        executor=executor,
        output_dir=out,
        open_artifacts=False,
    )
    assert result.handled and result.completed
    assert result.artifacts and result.artifacts[0].endswith(".txt")
    saved = out / result.artifacts[0]
    assert saved.exists()
    text = saved.read_text(encoding="utf-8-sig")
    assert "《" in text and "》" in text
    assert "《" in result.answer


def test_run_paint_drawing_uses_cat_fallback_when_api_unavailable(workdir, runner: TaskSkillRunner):
    executor = MockExecutor(AgentConfig())
    out = workdir / "out"

    result = runner.run(
        "paint_drawing",
        "用画图工具画一只猫",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=out,
        open_artifacts=False,
    )

    assert result.handled and result.completed
    assert not result.artifacts
    assert executor.executed[0]["type"] == "launch_app"
    assert executor.executed[0]["app"] == "paint"
    assert any(item.get("type") == "maximize_app" and item.get("app") == "paint" for item in executor.executed)
    drag_actions = [item for item in executor.executed if item.get("type") == "relative_drag"]
    assert len(drag_actions) >= 80
    assert all(item.get("app") == "paint" for item in drag_actions)
    assert all(0 <= float(item.get("relative_x")) <= 1 for item in drag_actions)
    assert all(0 <= float(item.get("end_relative_x")) <= 1 for item in drag_actions)
    assert "拖拽" in result.answer and "逐笔" in result.answer
    assert "内置猫咪兜底笔画" in result.answer


def test_run_paint_drawing_uses_model_generated_strokes(workdir, monkeypatch):
    config = AgentConfig(
        model_provider="openai_compatible",
        model_base_url="https://api.example.com/v1",
        model_api_key="test-key",
    )
    executor = MockExecutor(config)
    captured: dict[str, str] = {}

    def fake_model_chat(config, system, user, *, max_tokens=700):
        captured["user"] = user
        return """
        {"description":"房子简笔画","strokes":[
          [[0.2,0.55],[0.5,0.25],[0.8,0.55],[0.2,0.55]],
          [[0.28,0.55],[0.28,0.85],[0.72,0.85],[0.72,0.55]],
          [[0.45,0.85],[0.45,0.68],[0.56,0.68],[0.56,0.85]],
          [[0.34,0.62],[0.42,0.62],[0.42,0.70],[0.34,0.70]],
          [[0.60,0.62],[0.68,0.62],[0.68,0.70],[0.60,0.70]]
        ]}
        """

    monkeypatch.setattr("desktop_agent.task_skills.model_chat", fake_model_chat)

    result = TaskSkillRunner(config).run(
        "paint_drawing",
        "用画图工具画一个房子",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=workdir / "out",
        open_artifacts=False,
    )

    assert result.handled and result.completed
    assert "房子" in captured["user"]
    assert "API 模型生成笔画计划" in result.answer
    drag_actions = [item for item in executor.executed if item.get("type") == "relative_drag"]
    assert len(drag_actions) == 15
    assert all(item.get("app") == "paint" for item in drag_actions)


def test_parse_model_strokes_accepts_json_comments_from_api():
    raw = """
    {
      "description": "simple house",
      "strokes": [
        [[0.3, 0.5], [0.3, 0.8]],  // left wall
        [[0.7, 0.5], [0.7, 0.8]],  // right wall
        [[0.3, 0.8], [0.5, 1.0]],  // roof
        [[0.7, 0.8], [0.5, 1.0]],  // roof
      ]
    }
    """

    strokes = _parse_model_strokes(raw)

    assert strokes is not None
    assert len(strokes) == 4


def test_run_paint_drawing_prefers_smart_gptsapi_models(workdir, monkeypatch):
    config = AgentConfig(
        model_provider="openai_compatible",
        model_base_url="https://api.gptsapi.net/v1",
        model_name="gpt-4o-mini",
        model_api_key="test-key",
    )
    executor = MockExecutor(config)
    attempted: list[str] = []

    def fake_model_chat(config, system, user, *, max_tokens=700):
        attempted.append(config.model_name)
        if config.model_name == "claude-opus-4-8":
            return "not json"
        return """
        {"description":"house","strokes":[
          [[0.2,0.55],[0.5,0.25]],
          [[0.5,0.25],[0.8,0.55]],
          [[0.28,0.55],[0.28,0.85]],
          [[0.72,0.55],[0.72,0.85]]
        ]}
        """

    monkeypatch.setattr("desktop_agent.task_skills.model_chat", fake_model_chat)

    result = TaskSkillRunner(config).run(
        "paint_drawing",
        "用画图工具画一个房子",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=workdir / "out",
        open_artifacts=False,
    )

    assert result.handled and result.completed
    assert attempted[:2] == ["claude-opus-4-8", "claude-sonnet-4-6"]
    assert "claude-sonnet-4-6" in result.answer


def test_run_paint_drawing_requires_model_for_non_fallback_subject(workdir, runner: TaskSkillRunner):
    executor = MockExecutor(AgentConfig())

    result = runner.run(
        "paint_drawing",
        "用画图工具画一辆汽车",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=workdir / "out",
        open_artifacts=False,
    )

    assert result.handled and not result.completed
    assert result.requires_human
    assert "没有可用的非本地 API 模型" in result.answer
    assert not [item for item in executor.executed if item.get("type") == "relative_drag"]


def test_run_clock_timer_alarm_opens_clock_in_dry_run(runner: TaskSkillRunner):
    config = AgentConfig(dry_run=True)
    executor = MockExecutor(config)

    result = TaskSkillRunner(config).run(
        "clock_timer_alarm",
        "用计时器定一个1分钟闹钟",
        executor=executor,
    )

    assert result.handled and result.completed
    assert executor.state.active_app == "clock"
    assert executor.executed[0]["type"] == "open_app_if_needed"
    assert executor.executed[0]["app"] == "clock"
    assert "1分钟" in result.answer


class _FakePageExecutor(MockExecutor):
    """MockExecutor whose browser_snapshot returns a fixed real-looking page."""

    def __init__(self, config, page_text: str):
        super().__init__(config)
        self._page_text = page_text

    def browser_snapshot(self):
        return {"url": "https://search.jd.com/Search?keyword=x", "title": "男士休闲裤", "text": self._page_text}


class _FakeTravelExecutor(MockExecutor):
    """Returns a different visual/OCR snapshot for each opened travel page."""

    def __init__(self, config, snapshots: list[dict]):
        super().__init__(config)
        self._snapshots = snapshots

    def visual_browser_decision(self, *, kind: str, index: int, prompt: str):
        if kind == "search_home":
            return {
                "state": "search_home",
                "search_box": {"x": 640, "y": 360},
                "visible_text": "Bing 搜索",
            }
        if kind == "search_results":
            return {
                "state": "search_results",
                "human_verification": False,
                "candidates": [
                    {
                        "label": snapshot.get("title", f"结果 {candidate_index}"),
                        "url": snapshot.get("url", ""),
                        "x": 360,
                        "y": 180 + candidate_index * 80,
                        "reason": "攻略结果",
                    }
                    for candidate_index, snapshot in enumerate(self._snapshots, start=1)
                ],
            }
        return {}

    def visual_page_snapshot(self, *, url: str, label: str, index: int):
        snapshot_index = max(0, min(index - 1, len(self._snapshots) - 1))
        snapshot = dict(self._snapshots[snapshot_index])
        snapshot.setdefault("url", url)
        snapshot.setdefault("title", label)
        return snapshot

    def browser_snapshot(self):
        index = max(0, len(self.state.browser_history) - 1)
        index = min(index, len(self._snapshots) - 1)
        snapshot = dict(self._snapshots[index])
        snapshot.setdefault("url", self.state.current_url)
        return snapshot


def test_run_shopping_pants_grounds_answer_in_real_page():
    # When the page has real content, the answer must reflect ONLY what is on it.
    page = "李宁 速干运动长裤 ¥159 元  海澜之家 商务休闲裤 ￥199  优衣库弹力裤 99元 " * 8
    executor = _FakePageExecutor(AgentConfig(), page)
    result = TaskSkillRunner(AgentConfig()).run("shopping_pants", "上购物网站搜索男性裤子并分析性价比", executor=executor)
    assert result.handled and result.completed
    # Brands/prices that ARE on the page appear; nothing fabricated is invented.
    assert "李宁" in result.answer and "海澜之家" in result.answer
    assert "¥159" in result.answer
    assert "性价比评分" not in result.answer  # no fabricated scoring
    assert "Lee" not in result.answer  # brand not on the page must not appear


def test_run_shopping_pants_is_honest_when_blocked(runner: TaskSkillRunner):
    # MockExecutor's snapshot text is tiny -> classified as empty/blocked.
    executor = MockExecutor(AgentConfig())
    result = runner.run("shopping_pants", "上购物网站搜索男性裤子并分析性价比", executor=executor)
    assert result.handled and result.completed
    assert executor.state.current_url is not None
    # Honest: it must NOT claim a fabricated ranking, and must say it lacked data.
    assert "性价比评分" not in result.answer
    assert ("未" in result.answer) or ("没有" in result.answer) or ("登录" in result.answer)


def test_run_travel_word_writes_docx(workdir, runner: TaskSkillRunner):
    executor = MockExecutor(AgentConfig())
    result = runner.run(
        "travel_word",
        "上网搜索北京旅游景点并给出3天旅游规划，用word写出来",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=workdir / "out",
        open_artifacts=False,
    )
    assert result.handled and result.completed
    assert result.artifacts and result.artifacts[0].endswith(".docx")
    saved = (workdir / "out") / result.artifacts[0]
    assert saved.exists() and zipfile.is_zipfile(saved)
    assert "第一天" in result.answer


def test_run_travel_notepad_opens_multiple_pages_and_writes_text(workdir, runner: TaskSkillRunner):
    snapshots = [
        {"url": "https://example.test/1", "title": "北京旅游攻略一", "text": "故宫 天安门 景山 王府井 预约 地铁 " * 20},
        {"url": "https://example.test/2", "title": "北京旅游攻略二", "text": "长城 八达岭 慕田峪 鸟巢 水立方 " * 20},
        {"url": "https://example.test/3", "title": "北京旅游攻略三", "text": "颐和园 圆明园 胡同 什刹海 南锣鼓巷 " * 20},
        {"url": "https://example.test/4", "title": "北京旅游攻略四", "text": "烤鸭 炸酱面 地铁 门票 预约 " * 20},
    ]
    executor = _FakeTravelExecutor(AgentConfig(), snapshots)

    result = runner.run(
        "travel_notepad",
        "打开浏览器搜索北京旅游攻略，阅读多个网页后总结，并把总结内容写在记事本上",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=workdir / "out",
        open_artifacts=False,
    )

    assert result.handled and result.completed
    gui_targets = [a.get("text") for a in executor.executed if a.get("type") == "browser_gui_open"]
    assert any("cn.bing.com/search?q=Beijing+travel+guide+3+day+itinerary" in str(text) for text in gui_targets)
    assert len([text for text in gui_targets if "bing.com/search?q=Beijing+travel+guide+3+day+itinerary" in str(text)]) >= 3
    assert len([a for a in executor.executed if a.get("type") == "click"]) >= 3
    assert not [a for a in executor.executed if a.get("type") == "hotkey" and a.get("keys") == ["alt", "left"]]
    assert not [a for a in executor.executed if a.get("type") == "browser_open"]
    assert result.artifacts and result.artifacts[0].endswith(".txt")
    saved = (workdir / "out") / result.artifacts[0]
    text = saved.read_text(encoding="utf-8-sig")
    assert "北京旅游攻略总结" in text
    assert "多模态视觉分析" in text
    assert "故宫" in text and "长城" in text and "颐和园" in text
    assert "读取 3 个页面" in result.answer


def test_run_travel_notepad_recovers_when_result_click_stays_on_search_page(workdir, runner: TaskSkillRunner):
    class MissedClickExecutor(_FakeTravelExecutor):
        def __init__(self, config, snapshots: list[dict]):
            super().__init__(config, snapshots)
            self.page_calls = 0

        def visual_page_snapshot(self, *, url: str, label: str, index: int):
            self.page_calls += 1
            if self.page_calls == 1:
                return {
                    "url": "https://www.bing.com/search?q=Beijing+travel+guide+3+day+itinerary",
                    "title": "Bing 搜索结果页",
                    "text": "北京 Beijing travel guide 约 24,600 个结果 网页 图片 视频",
                }
            snapshot_index = max(0, min(self.page_calls - 2, len(self._snapshots) - 1))
            snapshot = dict(self._snapshots[snapshot_index])
            snapshot.setdefault("url", url)
            snapshot.setdefault("title", label)
            return snapshot

    snapshots = [
        {"url": "https://example.test/1", "title": "北京旅游攻略一", "text": "故宫 天安门 景山 王府井 预约 地铁 " * 20},
        {"url": "https://example.test/2", "title": "北京旅游攻略二", "text": "长城 八达岭 慕田峪 鸟巢 水立方 " * 20},
        {"url": "https://example.test/3", "title": "北京旅游攻略三", "text": "颐和园 圆明园 胡同 什刹海 南锣鼓巷 " * 20},
    ]
    executor = MissedClickExecutor(AgentConfig(), snapshots)

    result = runner.run(
        "travel_notepad",
        "北京旅游多页阅读写记事本",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=workdir / "out",
        open_artifacts=False,
    )

    assert result.handled and result.completed
    assert executor.page_calls >= 3
    assert len([a for a in executor.executed if a.get("type") == "click"]) >= 3
    assert "2 个页面读取到有效正文" in result.answer or "3 个页面读取到有效正文" in result.answer


def test_run_travel_notepad_uses_model_summary_when_available(workdir, monkeypatch):
    snapshots = [
        {"url": "https://example.test/1", "title": "北京旅游攻略一", "text": "故宫 天安门 景山 王府井 预约 地铁 " * 20},
        {"url": "https://example.test/2", "title": "北京旅游攻略二", "text": "长城 八达岭 慕田峪 鸟巢 水立方 " * 20},
        {"url": "https://example.test/3", "title": "北京旅游攻略三", "text": "颐和园 圆明园 胡同 什刹海 南锣鼓巷 " * 20},
        {"url": "https://example.test/4", "title": "北京旅游攻略四", "text": "烤鸭 炸酱面 地铁 门票 预约 " * 20},
    ]
    executor = _FakeTravelExecutor(AgentConfig(), snapshots)
    captured: dict[str, str] = {}

    def fake_model_chat(config, system, user, *, max_tokens=700):
        captured["system"] = system
        captured["user"] = user
        captured["max_tokens"] = str(max_tokens)
        return "API建议：第一天故宫和景山，第二天长城，第三天颐和园和胡同。"

    monkeypatch.setattr("desktop_agent.task_skills.model_chat", fake_model_chat)

    result = TaskSkillRunner(AgentConfig()).run(
        "travel_notepad",
        "打开浏览器搜索北京旅游攻略，阅读多个网页后总结，并把总结内容写在记事本上",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=workdir / "out",
        open_artifacts=False,
    )

    assert result.handled and result.completed
    assert "故宫 天安门" in captured["user"]
    assert "长城 八达岭" in captured["user"]
    saved = (workdir / "out") / result.artifacts[0]
    text = saved.read_text(encoding="utf-8-sig")
    assert "API 综合建议" in text
    assert "API建议：第一天故宫和景山" in text


def test_run_travel_notepad_does_not_complete_with_one_readable_page(workdir, runner: TaskSkillRunner):
    snapshots = [
        {"url": "https://example.test/1", "title": "空页面", "text": ""},
        {"url": "https://example.test/2", "title": "仍在加载", "text": "短"},
        {"url": "https://example.test/3", "title": "北京旅游攻略", "text": "故宫 八达岭长城 颐和园 烤鸭 " * 20},
        {"url": "https://example.test/4", "title": "拦截", "text": ""},
    ]
    executor = _FakeTravelExecutor(AgentConfig(), snapshots)

    result = runner.run(
        "travel_notepad",
        "打开浏览器搜索北京旅游攻略，阅读多个网页后总结，并把总结内容写在记事本上",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=workdir / "out",
        open_artifacts=False,
    )

    assert result.handled and not result.completed
    assert result.error == "insufficient readable travel pages"
    assert "有效网页不足" in result.answer
    saved = (workdir / "out") / result.artifacts[0]
    text = saved.read_text(encoding="utf-8-sig")
    assert "未生成最终攻略" in text
    assert "二、综合建议" not in text


def test_run_travel_notepad_rejects_non_target_ocr_window(workdir, runner: TaskSkillRunner):
    snapshots = [
        {
            "url": "https://example.test/wrong",
            "title": "Codex",
            "text": "修复悬浮窗并增强 computeruse desktop_agent_project PROGRESS 打开浏览器搜索北京旅游攻略",
        }
        for _ in range(4)
    ]
    executor = _FakeTravelExecutor(AgentConfig(), snapshots)

    result = runner.run(
        "travel_notepad",
        "打开浏览器搜索北京旅游攻略，阅读多个网页后总结，并把总结内容写在记事本上",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=workdir / "out",
        open_artifacts=False,
    )

    assert result.handled and not result.completed
    assert result.error == "insufficient readable travel pages"
    saved = (workdir / "out") / result.artifacts[0]
    text = saved.read_text(encoding="utf-8-sig")
    assert "当前工作窗口" in text
    assert "本次已成功读取 4 个网页" not in text


def test_run_travel_notepad_rejects_bing_image_preview(workdir, runner: TaskSkillRunner):
    snapshots = [
        {
            "url": "https://www.bing.com/images/search?view=detail",
            "title": "Ultimate Beijing 3-Day Itinerary",
            "text": "访问网站 此网站上的更多图像 视觉搜索 保存 查看图片 Beijing itinerary",
        }
        for _ in range(4)
    ]
    executor = _FakeTravelExecutor(AgentConfig(), snapshots)

    result = runner.run(
        "travel_notepad",
        "打开浏览器搜索北京旅游攻略，阅读多个网页后总结，并把总结内容写在记事本上",
        executor=executor,
        run_dir=workdir / "run",
        output_dir=workdir / "out",
        open_artifacts=False,
    )

    assert result.handled and not result.completed
    saved = (workdir / "out") / result.artifacts[0]
    text = saved.read_text(encoding="utf-8-sig")
    assert "图片预览层" in text
    assert "本次已成功读取 4 个网页" not in text


def test_run_travel_notepad_pauses_on_verification(runner: TaskSkillRunner):
    snapshots = [
        {
            "url": "https://www.baidu.com/s?wd=x",
            "title": "百度安全验证",
            "text": "请完成安全验证后继续访问",
        },
        {"url": "https://example.test/2", "title": "北京攻略", "text": "故宫 " * 100},
    ]
    executor = _FakeTravelExecutor(AgentConfig(), snapshots)

    result = runner.run(
        "travel_notepad",
        "打开浏览器搜索北京旅游攻略，阅读多个网页后总结，并把总结内容写在记事本上",
        executor=executor,
    )

    assert result.handled and not result.completed
    assert result.requires_human is True
    assert result.interruption_kind == "generic_human_verification"
    assert "人机验证" in result.answer or "安全验证" in result.answer
    assert [a for a in executor.executed if a.get("type") == "click"]
    assert not [a for a in executor.executed if a.get("type") == "browser_open"]


def test_run_qq_group_message_executes_search_and_send(runner: TaskSkillRunner):
    executor = MockExecutor(AgentConfig())

    result = runner.run(
        "qq_group_message",
        "打开QQ在群聊“项目演示群”发送消息“今天的演示已准备好”",
        executor=executor,
    )

    assert result.handled and result.completed
    assert executor.state.active_app == "qq"
    types = [item["type"] for item in executor.executed]
    assert types[:4] == ["open_app_if_needed", "wait", "hotkey", "wait"]
    typed = [item.get("text") for item in executor.executed if item.get("type") == "type"]
    assert typed == ["项目演示群", "今天的演示已准备好"]
    assert [item.get("key") for item in executor.executed if item.get("type") == "press"].count("enter") == 2


def test_run_qq_group_message_pauses_when_group_not_verified(runner: TaskSkillRunner):
    class UnverifiedQQExecutor(MockExecutor):
        def qq_group_verification(self, *, group_name: str):
            return {"matched": False, "reason": f"未看到目标群聊 {group_name}"}

    executor = UnverifiedQQExecutor(AgentConfig(dry_run=False))

    result = runner.run(
        "qq_group_message",
        "打开QQ在群聊“项目演示群”发送消息“今天的演示已准备好”",
        executor=executor,
    )

    assert result.handled and not result.completed
    assert result.requires_human is True
    assert result.interruption_kind == "qq_group_verification"
    typed = [item.get("text") for item in executor.executed if item.get("type") == "type"]
    assert typed == ["项目演示群"]


def test_run_qq_group_message_requires_group_and_message(runner: TaskSkillRunner):
    executor = MockExecutor(AgentConfig())

    result = runner.run("qq_group_message", "打开QQ在群聊发送消息", executor=executor)

    assert result.handled and not result.completed
    assert executor.executed == []
    assert "缺少" in result.answer


def test_run_calculator_invalid_expression_reports_gracefully(runner: TaskSkillRunner):
    executor = MockExecutor(AgentConfig())
    result = runner.run("calculator", "用计算器算 5/0", executor=executor)
    assert result.handled and not result.completed
    assert "无法" in result.answer


# --- controller fast-path integration -------------------------------------


def _build_headless_agent(workdir):
    import json

    from desktop_agent.controller import DesktopAgent
    from desktop_agent.logger import RunLogger
    from desktop_agent.perception import MockCapture
    from desktop_agent.planner import build_planner
    from desktop_agent.safety import ActionGuard

    config = AgentConfig(dry_run=False, planner_mode="rule", run_root=workdir / "runs")
    agent = DesktopAgent(
        config=config,
        planner=build_planner(config),
        executor=MockExecutor(config),
        perception=MockCapture(config=config),
        logger=RunLogger(config.run_root),
        guard=ActionGuard(config),
    )
    return agent, config, json


def test_controller_fast_path_emits_answer(workdir):
    agent, _config, json = _build_headless_agent(workdir)
    progress: list[dict] = []
    agent.progress_callback = lambda payload: progress.append(payload)

    result = agent.run("打开计算器计算1+1")

    assert result.completed is True
    assert result.skill == "calculator"
    assert result.answer and "= 2" in result.answer
    # summary.json persists the spoken answer for history/UI.
    summary = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["answer"] == result.answer
    assert summary["skill"] == "calculator"
    # The final progress payload carries the answer so the conversation can speak it.
    assert any("= 2" in str(item.get("answer") or "") for item in progress)


def test_controller_fast_path_skipped_in_dry_run(workdir):
    # When dry-run is on, the skill fast-path must defer to the normal loop so
    # existing mock-mode behaviour is preserved.
    from desktop_agent.controller import build_agent

    config_dry = AgentConfig(dry_run=True, planner_mode="rule", run_root=workdir / "dry")
    agent = build_agent(config_dry)
    assert agent._maybe_run_task_skill(
        task="打开计算器计算1+1",
        run_dir=workdir / "dry-run-dir",
        started_at=0.0,
        execution_state=None,
        step_offset=0,
    ) is None


def test_controller_fast_path_can_resume_skill_without_execution_state(workdir):
    agent, _config, json = _build_headless_agent(workdir)
    run_dir = workdir / "resume-skill-run"
    run_dir.mkdir()

    result = agent._maybe_run_task_skill(
        task="打开计算器计算1+1",
        run_dir=run_dir,
        started_at=0.0,
        execution_state=None,
        step_offset=3,
    )

    assert result is not None
    assert result.completed is True
    assert result.skill == "calculator"
    assert (run_dir / "step_04.json").exists()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["skill"] == "calculator"
