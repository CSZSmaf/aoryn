from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from desktop_agent.actions import Action


PLUGIN_PACKAGE = "desktop_agent.task_plugins"


@dataclass(slots=True)
class PluginManifest:
    id: str
    name: str
    description: str = ""
    app: str = ""
    version: str = "1.0.0"
    triggers: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    demo_task: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PluginManifest":
        plugin_id = str(payload.get("id") or "").strip()
        name = str(payload.get("name") or plugin_id).strip()
        if not plugin_id:
            raise ValueError("Plugin manifest requires id.")
        if not name:
            raise ValueError("Plugin manifest requires name.")
        return cls(
            id=plugin_id,
            name=name,
            description=str(payload.get("description") or "").strip(),
            app=str(payload.get("app") or "").strip(),
            version=str(payload.get("version") or "1.0.0").strip(),
            triggers=_string_list(payload.get("triggers")),
            capabilities=_string_list(payload.get("capabilities")),
            demo_task=str(payload.get("demo_task") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "app": self.app,
            "version": self.version,
            "triggers": list(self.triggers),
            "capabilities": list(self.capabilities),
            "demo_task": self.demo_task,
        }


@dataclass(slots=True)
class PluginRunResult:
    completed: bool
    answer: str
    headline: str
    actions: list[Action] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None
    requires_human: bool = False
    interruption_kind: str | None = None
    interruption_reason: str | None = None


@dataclass(slots=True)
class TaskPluginEntry:
    manifest: PluginManifest
    module: Any

    @property
    def id(self) -> str:
        return self.manifest.id

    def match(self, task: str, *, config: Any | None = None) -> bool:
        matcher = getattr(self.module, "match_task", None)
        if callable(matcher):
            try:
                return bool(matcher(task, manifest=self.manifest, config=config))
            except TypeError:
                return bool(matcher(task))
        lowered = str(task or "").lower()
        return any(trigger.lower() in lowered for trigger in self.manifest.triggers)

    def run(self, task: str, context: Any, *, config: Any | None = None) -> PluginRunResult:
        runner = getattr(self.module, "run_task", None)
        if not callable(runner):
            raise RuntimeError(f"Plugin {self.id} has no run_task callable.")
        result = runner(task, context, manifest=self.manifest, config=config)
        if isinstance(result, PluginRunResult):
            return result
        if isinstance(result, dict):
            return PluginRunResult(
                completed=bool(result.get("completed")),
                answer=str(result.get("answer") or ""),
                headline=str(result.get("headline") or ""),
                actions=list(result.get("actions") or []),
                artifacts=list(result.get("artifacts") or []),
                error=result.get("error"),
                requires_human=bool(result.get("requires_human")),
                interruption_kind=result.get("interruption_kind"),
                interruption_reason=result.get("interruption_reason"),
            )
        raise RuntimeError(f"Plugin {self.id} returned an unsupported result.")

    def status(self, *, config: Any | None = None) -> dict[str, Any]:
        status_fn = getattr(self.module, "status", None)
        if callable(status_fn):
            try:
                payload = status_fn(manifest=self.manifest, config=config)
                if isinstance(payload, dict):
                    return payload
            except TypeError:
                payload = status_fn()
                if isinstance(payload, dict):
                    return payload
            except Exception as exc:
                return {"state": "error", "label": "Error", "detail": str(exc)}
        return {"state": "available", "label": "Available", "detail": ""}

    def to_catalog_item(self, *, config: Any | None = None) -> dict[str, Any]:
        payload = self.manifest.to_dict()
        payload["status"] = self.status(config=config)
        return payload


def discover_task_plugins() -> list[TaskPluginEntry]:
    root = Path(__file__).resolve().parent / "task_plugins"
    if not root.exists():
        return []
    entries: list[TaskPluginEntry] = []
    for manifest_path in sorted(root.glob("*/plugin.json")):
        plugin_dir = manifest_path.parent
        try:
            manifest = PluginManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
            module = importlib.import_module(f"{PLUGIN_PACKAGE}.{plugin_dir.name}.plugin")
        except Exception:
            continue
        entries.append(TaskPluginEntry(manifest=manifest, module=module))
    return entries


def get_task_plugin(plugin_id: str) -> TaskPluginEntry | None:
    wanted = str(plugin_id or "").strip()
    if not wanted:
        return None
    for plugin in discover_task_plugins():
        if plugin.id == wanted:
            return plugin
    return None


def match_task_plugin(task: str, *, config: Any | None = None) -> TaskPluginEntry | None:
    for plugin in discover_task_plugins():
        if plugin.match(task, config=config):
            return plugin
    return None


def plugin_catalog(*, config: Any | None = None) -> list[dict[str, Any]]:
    return [plugin.to_catalog_item(config=config) for plugin in discover_task_plugins()]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
