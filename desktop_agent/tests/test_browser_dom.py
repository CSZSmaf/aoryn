import pytest

from desktop_agent.browser_dom import (
    BrowserDOMCancelled,
    PlaywrightBrowserSession,
    dom_backend_status,
    normalize_interactive_elements,
)
from desktop_agent.config import AgentConfig


def test_dom_backend_status_reports_missing_or_available_backend():
    status = dom_backend_status("playwright")

    assert status.backend == "playwright"
    assert isinstance(status.available, bool)
    assert status.detail


def test_dom_wait_polling_honors_stop_request():
    checks = {"count": 0}

    def stop_requested() -> bool:
        checks["count"] += 1
        return checks["count"] >= 3

    class FakeLocator:
        def __init__(self) -> None:
            self.timeouts: list[int] = []

        def wait_for(self, *, state: str, timeout: int) -> None:
            self.timeouts.append(timeout)
            raise TimeoutError("not visible yet")

    session = PlaywrightBrowserSession(AgentConfig(browser_dom_timeout=4), stop_requested=stop_requested)
    locator = FakeLocator()

    with pytest.raises(BrowserDOMCancelled):
        session._wait_for_visible(locator, 2000)

    assert locator.timeouts
    assert max(locator.timeouts) <= session._POLL_TIMEOUT_MS


def test_dom_navigation_timeout_is_bounded():
    timeouts: list[int] = []

    class FakePage:
        def goto(self, target: str, *, wait_until: str, timeout: int) -> None:
            timeouts.append(timeout)

    session = PlaywrightBrowserSession(AgentConfig(browser_dom_timeout=12))
    session._ensure_page = lambda: FakePage()

    session.open_url("example.com")

    assert timeouts == [session._MAX_NAVIGATION_MS]


def test_normalize_interactive_elements_compacts_visible_targets():
    raw_items = [
        "skip",
        {"selector": "", "label": "missing selector"},
        {
            "selector": "button[data-test=\"submit\"]",
            "label": "  Submit   order  ",
            "role": "button",
            "tag": "button",
            "disabled": False,
            "rect": {"x": 10.2, "y": 20.8, "width": 99.7, "height": 32},
        },
        {
            "selector": "input[name=\"q\"]",
            "placeholder": "Search",
            "role": "textbox",
            "tag": "input",
            "type": "search",
            "disabled": True,
        },
    ]

    normalized = normalize_interactive_elements(raw_items)

    assert [item["index"] for item in normalized] == [0, 1]
    assert normalized[0]["label"] == "Submit order"
    assert normalized[0]["selector"] == 'button[data-test="submit"]'
    assert normalized[0]["rect"] == {"x": 10, "y": 21, "width": 100, "height": 32}
    assert normalized[1]["label"] == "Search"
    assert normalized[1]["type"] == "search"
    assert normalized[1]["disabled"] is True


def test_snapshot_includes_interactive_elements_from_page():
    class FakeBodyLocator:
        def inner_text(self, *, timeout: int) -> str:
            assert timeout <= 800
            return "Search page body"

    class FakePage:
        url = "https://example.test/search"

        def title(self) -> str:
            return "Example Search"

        def locator(self, selector: str):
            assert selector == "body"
            return FakeBodyLocator()

        def evaluate(self, script: str):
            assert "querySelectorAll" in script
            return [
                {
                    "selector": "input[name=\"q\"]",
                    "label": "Search",
                    "role": "textbox",
                    "tag": "input",
                }
            ]

    session = PlaywrightBrowserSession(AgentConfig(browser_dom_timeout=2))
    session._page = FakePage()

    snapshot = session.snapshot()

    assert snapshot == {
        "url": "https://example.test/search",
        "title": "Example Search",
        "text": "Search page body",
        "interactive_elements": [
            {
                "index": 0,
                "selector": 'input[name="q"]',
                "label": "Search",
                "role": "textbox",
                "tag": "input",
                "disabled": False,
            }
        ],
    }
