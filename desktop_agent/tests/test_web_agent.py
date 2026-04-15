from desktop_agent.web_agent import WebAgent


class _FakeResponse:
    def __init__(self, *, url: str, text: str, content_type: str = "text/html; charset=utf-8") -> None:
        self.url = url
        self.text = text
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


class _FakeRequests:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def get(self, *args, **kwargs):
        return self._response


class _RaisingRequests:
    def get(self, *args, **kwargs):
        raise RuntimeError("network error")


def test_web_agent_plans_browser_search():
    agent = WebAgent()
    plan = agent.try_plan("search for OpenAI desktop agent")
    assert plan is not None
    assert plan.done is True
    assert plan.actions[0].type == "browser_search"
    assert plan.actions[0].text == "OpenAI desktop agent"


def test_web_agent_plans_marketplace_shopping_search():
    agent = WebAgent()

    plan = agent.try_plan("shop for high-value men's pants on amazon")

    assert plan is not None
    assert plan.done is True
    assert plan.actions[0].type == "browser_open"
    assert plan.actions[0].text.startswith("https://www.amazon.com/s?k=")
    assert "shopping results" in plan.status_summary.lower()


def test_web_agent_plans_generic_shopping_search():
    agent = WebAgent()

    plan = agent.try_plan("上购物网站搜索高性价比男性裤子")

    assert plan is not None
    assert plan.done is True
    assert plan.actions[0].type == "browser_search"
    assert "购物" in (plan.actions[0].text or "")


def test_web_agent_plans_open_url():
    agent = WebAgent(requests_module=_RaisingRequests())
    plan = agent.try_plan("visit openai.com/docs")
    assert plan is not None
    assert plan.actions[0].type == "browser_open"
    assert plan.actions[0].text == "https://openai.com/docs"


def test_web_agent_plans_launch_browser():
    agent = WebAgent()
    plan = agent.try_plan("open the browser")
    assert plan is not None
    assert [action.type for action in plan.actions] == ["open_app_if_needed", "wait"]


def test_web_agent_enriches_open_url_with_html_metadata():
    html = """
    <html>
      <head>
        <title>Example Docs</title>
        <meta name="description" content="Reference documentation home page.">
      </head>
      <body>
        <h1>API Reference</h1>
        <h2>Quickstart</h2>
        <button>Accept all</button>
        <button>Reject all</button>
      </body>
    </html>
    """
    agent = WebAgent(
        requests_module=_FakeRequests(
            _FakeResponse(url="https://example.com/docs/index.html", text=html)
        )
    )

    plan = agent.try_plan("visit example.com/docs")

    assert plan is not None
    assert plan.actions[0].type == "browser_open"
    assert plan.actions[0].text == "https://example.com/docs/index.html"
    assert "Expected page title: Example Docs." in plan.status_summary

    context = agent.build_task_context("visit example.com/docs")
    assert context is not None
    assert "Fetched page title: Example Docs" in context
    assert "Fetched headings: API Reference, Quickstart" in context
    assert "Possible popup: cookie_consent" in context
    assert "Reject all" in context


def test_web_agent_builds_navigation_plan_for_follow_up_browser_task():
    agent = WebAgent(requests_module=_RaisingRequests())

    plan = agent.build_navigation_plan("visit example.com and click login")

    assert plan is not None
    assert plan.done is False
    assert plan.actions[0].type == "browser_open"
    assert plan.actions[0].text == "https://example.com"
    assert "Then continue with: click login." in plan.status_summary
    assert plan.current_focus == "open https://example.com"
    assert plan.remaining_steps == ["click login"]


def test_web_agent_builds_navigation_plan_for_shopping_follow_up():
    agent = WebAgent()

    plan = agent.build_navigation_plan("shop for high-value men's pants on amazon and sort by price low to high")

    assert plan is not None
    assert plan.done is False
    assert plan.actions[0].type == "browser_open"
    assert plan.actions[0].text.startswith("https://www.amazon.com/s?k=")
    assert "sort by price low to high" in plan.status_summary
    assert plan.remaining_steps == ["sort by price low to high"]


def test_web_agent_builds_dom_follow_up_click_plan():
    agent = WebAgent(requests_module=_RaisingRequests())

    plan = agent.build_dom_follow_up_plan(
        "visit example.com and click login",
        history=["Open https://example.com in the browser. Then continue with: click login."],
    )

    assert plan is not None
    assert plan.done is True
    assert plan.actions[0].type == "browser_dom_click"
    assert plan.actions[0].text == "login"
    assert "Complete the browser task" in plan.status_summary
    assert plan.current_focus == "click login"
    assert plan.remaining_steps == []


def test_web_agent_prefers_popup_resolution_before_follow_up():
    html = """
    <html>
      <body>
        <button>Reject all</button>
        <button>Accept all</button>
        <button>Login</button>
      </body>
    </html>
    """
    agent = WebAgent(
        requests_module=_FakeRequests(
            _FakeResponse(url="https://example.com", text=html)
        )
    )

    plan = agent.build_dom_follow_up_plan(
        "visit example.com and click login",
        history=["Open https://example.com in the browser. Then continue with: click login."],
    )

    assert plan is not None
    assert plan.done is False
    assert plan.actions[0].type == "browser_dom_click"
    assert plan.actions[0].text == "Reject all"
    assert plan.current_focus == "dismiss the cookie_consent popup"
    assert plan.remaining_steps == ["click login"]


def test_web_agent_uses_html_action_label_for_follow_up_dom_click():
    html = """
    <html>
      <body>
        <a href="/login">Log in</a>
      </body>
    </html>
    """
    agent = WebAgent(
        requests_module=_FakeRequests(
            _FakeResponse(url="https://example.com", text=html)
        )
    )

    plan = agent.build_dom_follow_up_plan(
        "visit example.com and click login",
        history=["Open https://example.com in the browser. Then continue with: click login."],
    )

    assert plan is not None
    assert plan.done is True
    assert plan.actions[0].type == "browser_dom_click"
    assert plan.actions[0].text == "Log in"


def test_web_agent_builds_dom_follow_up_for_sorting_phrase():
    agent = WebAgent(requests_module=_RaisingRequests())

    plan = agent.build_dom_follow_up_plan(
        "shop for high-value men's pants on amazon and sort by price low to high",
        history=["Open shopping results for high-value men's pants on amazon."],
    )

    assert plan is not None
    assert plan.done is True
    assert plan.actions[0].type == "browser_dom_click"
    assert plan.actions[0].text == "price low to high"


def test_web_agent_splits_multi_step_follow_up_sequence():
    agent = WebAgent(requests_module=_RaisingRequests())

    plan = agent.build_navigation_plan(
        "shop for high-value men's pants on amazon and filter by style and choose black and sort by price low to high"
    )

    assert plan is not None
    assert plan.done is False
    assert "filter by style" in plan.status_summary.lower()
    assert "choose black" in plan.status_summary.lower()
    assert "sort by price low to high" in plan.status_summary.lower()


def test_web_agent_advances_multi_step_follow_up_based_on_history():
    agent = WebAgent(requests_module=_RaisingRequests())
    task = "shop for high-value men's pants on amazon and filter by style and choose black and sort by price low to high"

    step_one = agent.build_dom_follow_up_plan(
        task,
        history=["Open shopping results for high-value men's pants on amazon."],
    )
    assert step_one is not None
    assert step_one.done is False
    assert step_one.actions[0].text == "style"
    assert step_one.current_focus == "filter by style"
    assert step_one.remaining_steps == ["choose black", "sort by price low to high"]

    step_two = agent.build_dom_follow_up_plan(
        task,
        history=[
            "Open shopping results for high-value men's pants on amazon.",
            step_one.status_summary,
        ],
    )
    assert step_two is not None
    assert step_two.done is False
    assert step_two.actions[0].text == "black"
    assert step_two.current_focus == "choose black"
    assert step_two.remaining_steps == ["sort by price low to high"]

    step_three = agent.build_dom_follow_up_plan(
        task,
        history=[
            "Open shopping results for high-value men's pants on amazon.",
            step_one.status_summary,
            step_two.status_summary,
        ],
    )
    assert step_three is not None
    assert step_three.done is True
    assert step_three.actions[0].text == "price low to high"
    assert step_three.current_focus == "sort by price low to high"
    assert step_three.remaining_steps == []


def test_web_agent_does_not_short_circuit_follow_up_browser_task():
    agent = WebAgent(requests_module=_RaisingRequests())

    plan = agent.try_plan("visit example.com and click login")

    assert plan is None


def test_web_agent_falls_back_to_raw_url_when_preflight_fails():
    agent = WebAgent(requests_module=_RaisingRequests())

    plan = agent.try_plan("visit example.com/docs")

    assert plan is not None
    assert plan.actions[0].type == "browser_open"
    assert plan.actions[0].text == "https://example.com/docs"
