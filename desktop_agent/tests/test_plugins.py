import sys
import types

from desktop_agent.actions import Action
from desktop_agent.capabilities import CapabilityAdapter
from desktop_agent.config import AgentConfig
from desktop_agent.controller import build_agent
from desktop_agent.drivers import AppDriver
from desktop_agent.plugins import build_runtime_registries
from desktop_agent.workflow import ExecutionState, StepProposal, Subgoal, TaskGraph, WorldModel


class _AcmeCapability(CapabilityAdapter):
    name = "acme_app"

    def can_handle(self, subgoal: Subgoal, world_model: WorldModel) -> float:
        return 0.7 if "acme" in (world_model.active_window_title or "").lower() else 0.0

    def plan_step(self, *, subgoal, world_model, execution_state, config, planner):
        return StepProposal(
            intent="Use Acme-specific stable automation.",
            actions=[Action.from_dict({"type": "wait", "seconds": 0.2})],
            capability=self.name,
        )


class _AcmeDriver(AppDriver):
    name = "acme_driver"

    def matches(self, world_model: WorldModel) -> bool:
        return "acme" in (world_model.active_window_title or "").lower()

    def preferred_capabilities(self) -> list[str]:
        return ["acme_app"]


def test_plugin_module_registers_driver_and_capability(monkeypatch):
    module = types.ModuleType("aoryn_test_acme_plugin")

    def register_plugin(context):
        context.register_driver(_AcmeDriver())
        context.register_capability(_AcmeCapability())

    module.register_plugin = register_plugin
    monkeypatch.setitem(sys.modules, module.__name__, module)

    config = AgentConfig(plugin_modules=[module.__name__])
    capability_registry, driver_registry, results = build_runtime_registries(config)

    assert results[0].loaded is True
    assert results[0].drivers == ["acme_driver"]
    assert results[0].capabilities == ["acme_app"]
    assert any(item.name == "acme_driver" for item in driver_registry.drivers)
    assert any(item.name == "acme_app" for item in capability_registry.capabilities)

    world_model = WorldModel(active_window_title="Acme Studio")
    subgoal = Subgoal(id="subgoal_01", title="click a stable Acme toolbar button")
    execution_state = ExecutionState(
        task="use Acme",
        run_id="run-plugins",
        task_graph=TaskGraph(task="use Acme", subgoals=[subgoal]),
    )
    ranked = capability_registry.rank(
        subgoal=subgoal,
        world_model=world_model,
        config=config,
        execution_state=execution_state,
        driver_registry=driver_registry,
    )

    assert ranked[0][0].name == "acme_app"


def test_plugin_load_failure_is_reported_without_breaking_defaults(monkeypatch):
    module = types.ModuleType("aoryn_test_empty_plugin")
    monkeypatch.setitem(sys.modules, module.__name__, module)

    capability_registry, driver_registry, results = build_runtime_registries(AgentConfig(plugin_modules=[module.__name__]))

    assert results[0].loaded is False
    assert "register_plugin" in (results[0].error or "")
    assert any(item.name == "desktop_gui" for item in capability_registry.capabilities)
    assert any(item.name == "browser" for item in driver_registry.drivers)


def test_build_agent_wires_plugin_registries(monkeypatch, tmp_path):
    module = types.ModuleType("aoryn_test_agent_plugin")

    def register_plugin(context):
        context.register_driver(_AcmeDriver())
        context.register_capability(_AcmeCapability())

    module.register_plugin = register_plugin
    monkeypatch.setitem(sys.modules, module.__name__, module)

    config = AgentConfig(dry_run=True, run_root=tmp_path / "runs", plugin_modules=[module.__name__])
    agent = build_agent(config)

    assert any(item.name == "acme_driver" for item in agent.driver_registry.drivers)
    assert any(item.name == "acme_app" for item in agent.capability_executor.registry.capabilities)


def test_builtin_notepad_plugin_types_requested_text():
    config = AgentConfig(plugin_modules=["desktop_agent.software_plugins.notepad"])
    capability_registry, driver_registry, results = build_runtime_registries(config)
    world_model = WorldModel(active_app="notepad", active_window_title="Untitled - Notepad")
    subgoal = Subgoal(id="subgoal_01", title="write hello from plugin")
    execution_state = ExecutionState(
        task="write in notepad",
        run_id="run-notepad-plugin",
        task_graph=TaskGraph(task="write in notepad", subgoals=[subgoal]),
    )

    assert results[0].loaded is True
    assert results[0].drivers == ["notepad"]
    assert results[0].capabilities == ["notepad_text"]

    ranked = capability_registry.rank(
        subgoal=subgoal,
        world_model=world_model,
        config=config,
        execution_state=execution_state,
        driver_registry=driver_registry,
    )
    proposal = ranked[0][0].propose_step(
        subgoal=subgoal,
        world_model=world_model,
        execution_state=execution_state,
        config=config,
        planner=None,
    )

    assert ranked[0][0].name == "notepad_text"
    assert proposal is not None
    assert proposal.actions[0].type == "type"
    assert proposal.actions[0].text == "hello from plugin"
