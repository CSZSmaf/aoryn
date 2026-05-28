from __future__ import annotations

import re
import time
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Callable

from desktop_agent.config import AgentConfig


class BrowserDOMError(RuntimeError):
    """Raised when DOM-based browser automation cannot continue."""


class BrowserDOMCancelled(BrowserDOMError):
    """Raised when a DOM operation is interrupted by the active run stop flag."""


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

    _POLL_TIMEOUT_MS = 200
    _TEXT_PROBE_TIMEOUT_MS = 500
    _MAX_BLOCKING_ACTION_MS = 1200
    _MAX_NAVIGATION_MS = 3000
    _MAX_POST_CLICK_WAIT_MS = 1500

    def __init__(self, config: AgentConfig, stop_requested: Callable[[], bool] | None = None):
        self.config = config
        self._stop_requested = stop_requested
        self._playwright = None
        self._browser = None
        self._page = None

    def set_stop_requested(self, stop_requested: Callable[[], bool] | None) -> None:
        self._stop_requested = stop_requested

    def open_url(self, target: str) -> None:
        self._ensure_not_stopped()
        page = self._ensure_page()
        normalized = target if target.strip().lower() == "about:blank" else self.config.normalize_browser_url(target)
        page.goto(
            normalized,
            wait_until="domcontentloaded",
            timeout=min(self._timeout_ms(), self._MAX_NAVIGATION_MS),
        )
        self._ensure_not_stopped()

    def search(self, query: str) -> None:
        self.open_url(self.config.build_browser_search_url(query))

    def click(self, *, text: str | None = None, selector: str | None = None) -> None:
        page = self._ensure_page()
        timeout_ms = self._timeout_ms()

        if selector:
            locator = page.locator(selector).first
            self._wait_for_visible(locator, timeout_ms)
            self._ensure_not_stopped()
            locator.click(timeout=self._action_timeout_ms(timeout_ms))
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
                self._wait_for_visible(locator, min(timeout_ms, self._TEXT_PROBE_TIMEOUT_MS))
                self._ensure_not_stopped()
                locator.click(timeout=self._action_timeout_ms(timeout_ms))
                self._wait_after_click(page, timeout_ms)
                return
            except BrowserDOMCancelled:
                raise
            except Exception:
                continue

        raise BrowserDOMError(f"Could not find a DOM target matching `{label}`.")

    def fill(self, *, value: str, text: str | None = None, selector: str | None = None) -> None:
        locator = self._resolve_locator(text=text, selector=selector)
        timeout_ms = self._timeout_ms()
        self._wait_for_visible(locator, timeout_ms)
        self._ensure_not_stopped()
        locator.fill(value, timeout=self._action_timeout_ms(timeout_ms))
        self._ensure_not_stopped()

    def select(self, *, value: str, text: str | None = None, selector: str | None = None) -> None:
        locator = self._resolve_locator(text=text, selector=selector)
        timeout_ms = self._timeout_ms()
        self._wait_for_visible(locator, timeout_ms)
        self._ensure_not_stopped()
        try:
            locator.select_option(value=value, timeout=self._action_timeout_ms(timeout_ms))
        except Exception:
            self._ensure_not_stopped()
            locator.select_option(label=value, timeout=self._action_timeout_ms(timeout_ms))
        self._ensure_not_stopped()

    def wait_for(self, *, text: str | None = None, selector: str | None = None, timeout_seconds: float | None = None) -> None:
        locator = self._resolve_locator(text=text, selector=selector)
        timeout_ms = self._timeout_ms(timeout_seconds or self.config.browser_dom_timeout)
        self._wait_for_visible(locator, timeout_ms)

    def extract(self, *, text: str | None = None, selector: str | None = None) -> str:
        locator = self._resolve_locator(text=text, selector=selector)
        timeout_ms = self._timeout_ms()
        self._wait_for_visible(locator, timeout_ms)
        try:
            return str(locator.inner_text(timeout=self._action_timeout_ms(timeout_ms)) or "").strip()
        except Exception:
            self._ensure_not_stopped()
            return str(locator.text_content(timeout=self._action_timeout_ms(timeout_ms)) or "").strip()

    def snapshot(self) -> dict[str, str | None] | None:
        self._ensure_not_stopped()
        if self._page is None:
            return None

        snapshot: dict[str, str | None] = {"url": None, "title": None, "text": None}
        try:
            snapshot["url"] = str(self._page.url or "").strip() or None
        except Exception:
            snapshot["url"] = None
        self._ensure_not_stopped()
        try:
            snapshot["title"] = str(self._page.title() or "").strip() or None
        except Exception:
            snapshot["title"] = None
        self._ensure_not_stopped()
        try:
            timeout_ms = min(self._timeout_ms(), 800)
            body_text = str(self._page.locator("body").inner_text(timeout=timeout_ms) or "").strip()
            if body_text:
                snapshot["text"] = body_text[:4000]
        except Exception:
            snapshot["text"] = None
        self._ensure_not_stopped()
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
        self._ensure_not_stopped()
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
        self._ensure_not_stopped()
        return self._page

    def _select_browser_type(self):
        if self._playwright is None:
            raise BrowserDOMError("Playwright session is not initialized.")
        channel = (self.config.browser_channel or "").lower()
        executable = (self.config.browser_executable_path or "").lower()
        if "firefox" in channel or "firefox" in executable:
            return self._playwright.firefox
        return self._playwright.chromium

    def _wait_after_click(self, page, timeout_ms: int) -> None:
        deadline = time.monotonic() + min(timeout_ms, self._MAX_POST_CLICK_WAIT_MS) / 1000
        while True:
            self._ensure_not_stopped()
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if remaining_ms <= 0:
                return
            try:
                page.wait_for_load_state("domcontentloaded", timeout=min(remaining_ms, self._POLL_TIMEOUT_MS))
                self._ensure_not_stopped()
                return
            except Exception:
                continue

    def _resolve_locator(self, *, text: str | None = None, selector: str | None = None):
        page = self._ensure_page()
        timeout_ms = self._timeout_ms()
        if selector:
            locator = page.locator(selector).first
            self._wait_for_visible(locator, timeout_ms)
            return locator

        label = (text or "").strip()
        if not label:
            raise BrowserDOMError("A text label or selector is required.")

        locators = [
            page.get_by_label(re.compile(re.escape(label), re.I)).first,
            page.get_by_placeholder(re.compile(re.escape(label), re.I)).first,
            page.get_by_role("textbox", name=re.compile(re.escape(label), re.I)).first,
            page.get_by_role("combobox", name=re.compile(re.escape(label), re.I)).first,
            page.get_by_role("option", name=re.compile(re.escape(label), re.I)).first,
            page.get_by_text(re.compile(re.escape(label), re.I)).first,
        ]
        for locator in locators:
            try:
                self._wait_for_visible(locator, min(timeout_ms, self._TEXT_PROBE_TIMEOUT_MS))
                return locator
            except BrowserDOMCancelled:
                raise
            except Exception:
                continue
        raise BrowserDOMError(f"Could not resolve a DOM locator matching `{label}`.")

    def _timeout_ms(self, seconds: float | None = None) -> int:
        value = self.config.browser_dom_timeout if seconds is None else seconds
        try:
            timeout_seconds = float(value)
        except (TypeError, ValueError):
            timeout_seconds = float(self.config.browser_dom_timeout)
        return max(100, int(timeout_seconds * 1000))

    def _action_timeout_ms(self, timeout_ms: int) -> int:
        return max(100, min(int(timeout_ms), self._MAX_BLOCKING_ACTION_MS))

    def _wait_for_visible(self, locator, timeout_ms: int) -> None:
        deadline = time.monotonic() + max(0, int(timeout_ms)) / 1000
        last_error: Exception | None = None
        while True:
            self._ensure_not_stopped()
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if remaining_ms <= 0:
                if last_error is not None:
                    raise last_error
                raise BrowserDOMError("Timed out waiting for a visible DOM target.")
            try:
                locator.wait_for(state="visible", timeout=min(remaining_ms, self._POLL_TIMEOUT_MS))
                self._ensure_not_stopped()
                return
            except BrowserDOMCancelled:
                raise
            except Exception as exc:
                last_error = exc

    def _ensure_not_stopped(self) -> None:
        if self._stop_requested is None:
            return
        try:
            requested = bool(self._stop_requested())
        except Exception:
            requested = False
        if requested:
            raise BrowserDOMCancelled("Stopped by user.")


def _optional_existing_path(path: str | None) -> str | None:
    candidate = (path or "").strip()
    if not candidate:
        return None
    if Path(candidate).is_file():
        return candidate
    return None
