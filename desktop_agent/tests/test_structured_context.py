from pathlib import Path

from desktop_agent.capabilities import BrowserDOMCapability, WindowsUIACapability
from desktop_agent.controller import _collect_anchor_candidates
from desktop_agent.workflow import WorldModel


def test_anchor_candidates_include_browser_elements_and_uia_controls():
    anchors = _collect_anchor_candidates(
        active_window_title="Demo App",
        browser_snapshot={
            "title": "Results",
            "url": "https://example.test",
            "interactive_elements": [
                {
                    "label": "Open details",
                    "role": "link",
                    "selector": "a#details",
                }
            ],
        },
        visible_windows=[{"title": "Other Window"}],
        uia_tree=[
            {
                "name": "Send",
                "control_type": "Button",
                "automation_id": "sendButton",
                "selector": "control_type=Button;auto_id=sendButton",
            }
        ],
        selection_text="selected note",
    )

    assert "Demo App" in anchors
    assert "Open details" in anchors
    assert "a#details" in anchors
    assert "Send" in anchors
    assert "sendButton" in anchors
    assert "control_type=Button;auto_id=sendButton" in anchors


def test_browser_dom_capability_observes_interactive_elements():
    world_model = WorldModel(
        screenshot_path=Path("demo.png"),
        browser_snapshot={
            "url": "https://example.test",
            "interactive_elements": [
                {
                    "index": 0,
                    "label": "Search",
                    "role": "textbox",
                    "selector": "input[name=\"q\"]",
                }
            ],
        },
    )

    capability = BrowserDOMCapability()

    facts = capability.observe(world_model)
    anchors = capability.extract_anchors(world_model)

    assert any(fact.key == "interactive_elements" and "Search" in fact.value for fact in facts)
    assert "Search" in anchors
    assert 'input[name="q"]' in anchors


def test_windows_uia_capability_uses_selectors_as_anchors():
    world_model = WorldModel(
        screenshot_path=Path("demo.png"),
        active_window_title="QQ",
        active_app="qq",
        uia_tree=[
            {
                "name": "Group Chat",
                "control_type": "ListItem",
                "automation_id": "group-chat",
                "selector": "control_type=ListItem;auto_id=group-chat",
            }
        ],
    )

    anchors = WindowsUIACapability().extract_anchors(world_model)

    assert "Group Chat" in anchors
    assert "group-chat" in anchors
    assert "control_type=ListItem;auto_id=group-chat" in anchors
