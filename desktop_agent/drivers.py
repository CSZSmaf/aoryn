from __future__ import annotations

from dataclasses import dataclass, field

from desktop_agent.workflow import EvidenceRequirement, ObservedFact, WorldModel


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


class AppDriver:
    name = "generic"

    def matches(self, world_model: WorldModel) -> bool:
        raise NotImplementedError

    def describe(self, world_model: WorldModel) -> list[ObservedFact]:
        return []

    def preferred_capabilities(self) -> list[str]:
        return []

    def verification_hints(self, world_model: WorldModel) -> list[EvidenceRequirement]:
        return []


@dataclass(slots=True)
class DriverRegistry:
    drivers: list[AppDriver] = field(default_factory=list)

    def register(self, driver: AppDriver) -> None:
        self.drivers.append(driver)

    def detect(self, world_model: WorldModel) -> AppDriver | None:
        for driver in self.drivers:
            try:
                if driver.matches(world_model):
                    return driver
            except Exception:
                continue
        return None

    def describe(self, world_model: WorldModel) -> list[ObservedFact]:
        driver = self.detect(world_model)
        if driver is None:
            return []
        return driver.describe(world_model)


class BrowserDriver(AppDriver):
    name = "browser"

    def matches(self, world_model: WorldModel) -> bool:
        active_app = _normalize_text(world_model.active_app)
        if active_app == "browser":
            return True
        browser_snapshot = world_model.browser_snapshot or {}
        return bool(str(browser_snapshot.get("url") or "").strip())

    def describe(self, world_model: WorldModel) -> list[ObservedFact]:
        browser_snapshot = world_model.browser_snapshot or {}
        facts: list[ObservedFact] = []
        if browser_snapshot.get("url"):
            facts.append(ObservedFact(source=self.name, key="browser_url", value=str(browser_snapshot["url"])))
        if browser_snapshot.get("title"):
            facts.append(ObservedFact(source=self.name, key="browser_title", value=str(browser_snapshot["title"])))
        return facts

    def preferred_capabilities(self) -> list[str]:
        return ["browser_dom", "clipboard", "filesystem", "desktop_gui"]

    def verification_hints(self, world_model: WorldModel) -> list[EvidenceRequirement]:
        hints: list[EvidenceRequirement] = []
        browser_snapshot = world_model.browser_snapshot or {}
        if browser_snapshot.get("url"):
            hints.append(
                EvidenceRequirement(
                    kind="browser_url_contains",
                    value=str(browser_snapshot["url"]),
                    detail="The browser URL should stay on the expected page.",
                    required=False,
                )
            )
        return hints


class OfficeDriver(AppDriver):
    name = "office"

    def matches(self, world_model: WorldModel) -> bool:
        title = _normalize_text(world_model.active_window_title)
        return any(token in title for token in ("excel", "powerpoint", "word"))

    def describe(self, world_model: WorldModel) -> list[ObservedFact]:
        title = str(world_model.active_window_title or "").strip()
        if not title:
            return []
        return [ObservedFact(source=self.name, key="office_window", value=title)]

    def preferred_capabilities(self) -> list[str]:
        return ["office_com", "windows_uia", "desktop_gui", "clipboard"]


class VSCodeDriver(AppDriver):
    name = "vscode"

    def matches(self, world_model: WorldModel) -> bool:
        title = _normalize_text(world_model.active_window_title)
        return any(token in title for token in ("visual studio code", "cursor", "vscode"))

    def describe(self, world_model: WorldModel) -> list[ObservedFact]:
        title = str(world_model.active_window_title or "").strip()
        if not title:
            return []
        return [ObservedFact(source=self.name, key="editor_window", value=title)]

    def preferred_capabilities(self) -> list[str]:
        return ["windows_uia", "guarded_shell_recipe", "clipboard", "desktop_gui"]


def build_driver_registry() -> DriverRegistry:
    registry = DriverRegistry()
    registry.register(BrowserDriver())
    registry.register(OfficeDriver())
    registry.register(VSCodeDriver())
    return registry
