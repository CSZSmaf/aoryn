import pytest

from desktop_agent.browser_dom import BrowserDOMCancelled, PlaywrightBrowserSession, dom_backend_status
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
