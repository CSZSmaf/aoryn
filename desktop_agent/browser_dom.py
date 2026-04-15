from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from desktop_agent.config import AgentConfig


class BrowserDOMError(RuntimeError):
    """Raised when DOM-based browser automation cannot continue."""


@dataclass(slots=True)
class BrowserDOMStatus:
    available: bool
    backend: str
    detail: str


def dom_backend_status(backend: str) -> BrowserDOMStatus:
    normalized = (backend or "playwright").strip().lower()
    if normalized != "playwright":
        return BrowserDOMStatus(
            available=False,
            backend=normalized,
            detail=f"Unsupported DOM backend: {normalized}",
        )
    if find_spec("playwright") is None:
        return BrowserDOMStatus(
            available=False,
            backend="playwright",
            detail="Playwright Python package is not installed.",
        )
    return BrowserDOMStatus(
        available=True,
        backend="playwright",
        detail="Playwright backend is available.",
    )


class PlaywrightBrowserSession:
    """Lazy Playwright browser session for DOM-first interactions."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self._playwright = None
        self._browser = None
        self._page = None

    def open_url(self, target: str) -> None:
        page = self._ensure_page()
        normalized = target if target.strip().lower() == "about:blank" else self.config.normalize_browser_url(target)
        page.goto(
            normalized,
            wait_until="domcontentloaded",
            timeout=int(self.config.browser_dom_timeout * 1000),
        )

    def search(self, query: str) -> None:
        self.open_url(self.config.build_browser_search_url(query))

    def click(self, *, text: str | None = None, selector: str | None = None) -> None:
        page = self._ensure_page()
        timeout_ms = int(self.config.browser_dom_timeout * 1000)

        if selector:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            locator.click(timeout=timeout_ms)
            self._wait_after_click(page, timeout_ms)
            return

        label = (text or "").strip()
        if not label:
            raise BrowserDOMError("browser_dom_click requires text or selector.")

        locators = [
            page.get_by_role("button", name=re.compile(re.escape(label), re.I)).first,
            page.get_by_role("link", name=re.compile(re.escape(label), re.I)).first,
            page.get_by_role("menuitem", name=re.compile(re.escape(label), re.I)).first,
            page.get_by_text(re.compile(re.escape(label), re.I)).first,
        ]

        for locator in locators:
            try:
                locator.wait_for(state="visible", timeout=1200)
                locator.click(timeout=timeout_ms)
                self._wait_after_click(page, timeout_ms)
                return
            except Exception:
                continue

        raise BrowserDOMError(f"Could not find a DOM target matching `{label}`.")

    def snapshot(self) -> dict[str, str | None] | None:
        if self._page is None:
            return None

        snapshot: dict[str, str | None] = {"url": None, "title": None, "text": None}
        try:
            snapshot["url"] = str(self._page.url or "").strip() or None
        except Exception:
            snapshot["url"] = None
        try:
            snapshot["title"] = str(self._page.title() or "").strip() or None
        except Exception:
            snapshot["title"] = None
        try:
            timeout_ms = min(int(self.config.browser_dom_timeout * 1000), 1200)
            body_text = str(self._page.locator("body").inner_text(timeout=timeout_ms) or "").strip()
            if body_text:
                snapshot["text"] = body_text[:4000]
        except Exception:
            snapshot["text"] = None
        return snapshot

    def close(self) -> None:
        if self._page is not None:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def _ensure_page(self):
        if self._page is not None:
            return self._page

        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise BrowserDOMError(
                "Playwright is not installed. Run `python -m pip install playwright` "
                "and then `python -m playwright install chromium` to enable DOM browser control."
            ) from exc

        self._playwright = sync_playwright().start()
        browser_type = self._select_browser_type()
        launch_kwargs = {"headless": bool(self.config.browser_headless)}
        executable_path = _optional_existing_path(self.config.browser_executable_path)
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        elif self.config.browser_channel and browser_type == self._playwright.chromium:
            launch_kwargs["channel"] = self.config.browser_channel

        try:
            self._browser = browser_type.launch(**launch_kwargs)
        except Exception as exc:
            self.close()
            raise BrowserDOMError(
                "Failed to launch the DOM browser session. If you just installed Playwright, "
                "also run `python -m playwright install chromium`."
            ) from exc

        self._page = self._browser.new_page()
        return self._page

    def _select_browser_type(self):
        if self._playwright is None:
            raise BrowserDOMError("Playwright session is not initialized.")
        channel = (self.config.browser_channel or "").lower()
        executable = (self.config.browser_executable_path or "").lower()
        if "firefox" in channel or "firefox" in executable:
            return self._playwright.firefox
        return self._playwright.chromium

    @staticmethod
    def _wait_after_click(page, timeout_ms: int) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            return


def _optional_existing_path(path: str | None) -> str | None:
    candidate = (path or "").strip()
    if not candidate:
        return None
    if Path(candidate).is_file():
        return candidate
    return None
