from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from desktop_agent.config import AgentConfig


@dataclass(slots=True)
class PluginLoadResult:
    module: str
    loaded: bool
    capabilities: list[str] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class PluginContext:
    config: AgentConfig
    capability_registry: Any | None = None
    driver_registry: Any | None = None
    capabilities: list[str] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)

    def register_capability(self, capability: Any) -> None:
        if self.capability_registry is None:
            return
        name = _plugin_item_name(capability, kind="capability")
        self.capability_registry.capabilities = [
            item
            for item in self.capability_registry.capabilities
            if str(getattr(item, "name", "")).strip().lower() != name.lower()
        ]
        self.capability_registry.register(capability)
        enabled = getattr(self.config, "enabled_capabilities", None)
        if isinstance(enabled, list) and all(str(item).strip().lower() != name.lower() for item in enabled):
            enabled.append(name)
        self.capabilities.append(name)

    def register_driver(self, driver: Any) -> None:
        if self.driver_registry is None:
            return
        name = _plugin_item_name(driver, kind="driver")
        self.driver_registry.drivers = [
            item
            for item in self.driver_registry.drivers
            if str(getattr(item, "name", "")).strip().lower() != name.lower()
        ]
        self.driver_registry.register(driver)
        self.drivers.append(name)


def load_configured_plugins(
    config: AgentConfig,
    *,
    capability_registry: Any | None = None,
    driver_registry: Any | None = None,
) -> list[PluginLoadResult]:
    results: list[PluginLoadResult] = []
    for module_name in _configured_plugin_modules(config):
        context = PluginContext(
            config=config,
            capability_registry=capability_registry,
            driver_registry=driver_registry,
        )
        try:
            module = importlib.import_module(module_name)
            _register_plugin_module(module, context)
        except Exception as exc:
            if bool(getattr(config, "plugin_fail_fast", False)):
                raise
            results.append(PluginLoadResult(module=module_name, loaded=False, error=str(exc)))
            continue
        results.append(
            PluginLoadResult(
                module=module_name,
                loaded=True,
                capabilities=list(context.capabilities),
                drivers=list(context.drivers),
            )
        )
    return results


def build_runtime_registries(config: AgentConfig):
    from desktop_agent.capabilities import build_capability_registry
    from desktop_agent.drivers import build_driver_registry

    capability_registry = build_capability_registry()
    driver_registry = build_driver_registry()
    results = load_configured_plugins(
        config,
        capability_registry=capability_registry,
        driver_registry=driver_registry,
    )
    return capability_registry, driver_registry, results


def _register_plugin_module(module: Any, context: PluginContext) -> None:
    registrar = getattr(module, "register_plugin", None) or getattr(module, "register", None)
    if callable(registrar):
        registrar(context)
        return

    registered = False
    for capability in getattr(module, "CAPABILITIES", []) or []:
        context.register_capability(capability)
        registered = True
    for driver in getattr(module, "DRIVERS", []) or []:
        context.register_driver(driver)
        registered = True
    if not registered:
        raise ValueError("Plugin module must expose register_plugin(context), register(context), CAPABILITIES, or DRIVERS.")


def _configured_plugin_modules(config: AgentConfig) -> list[str]:
    raw_modules = getattr(config, "plugin_modules", []) or []
    if isinstance(raw_modules, str):
        raw_items = raw_modules.replace(";", ",").split(",")
    elif isinstance(raw_modules, (list, tuple, set)):
        raw_items = raw_modules
    else:
        raw_items = []
    modules: list[str] = []
    for item in raw_items:
        module_name = str(item or "").strip()
        if module_name and module_name not in modules:
            modules.append(module_name)
    return modules


def _plugin_item_name(item: Any, *, kind: str) -> str:
    name = str(getattr(item, "name", "") or "").strip()
    if not name:
        raise ValueError(f"Plugin {kind} must define a non-empty name.")
    return name
