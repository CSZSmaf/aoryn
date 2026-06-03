from __future__ import annotations

from collections import deque
from typing import Any


def capture_uia_tree(
    *,
    active_window_title: str | None = None,
    max_depth: int = 3,
    max_items: int = 80,
) -> list[dict[str, Any]]:
    """Capture a compact Microsoft UI Automation tree for the active window.

    This mirrors the approach used by pywinauto/WinAppDriver/FlaUI style tools:
    rely on UIA metadata first (name, control type, automation id), then fall
    back to screenshots only when native controls are unavailable.
    """

    try:
        from pywinauto import Desktop
    except Exception:
        return []

    try:
        desktop = Desktop(backend="uia")
        title = " ".join(str(active_window_title or "").split()).strip()
        if title:
            root = desktop.window(title_re=f".*{_escape_title_fragment(title)}.*").wrapper_object()
        else:
            root = desktop.active()
    except Exception:
        return []
    return flatten_uia_tree(root, max_depth=max_depth, max_items=max_items)


def flatten_uia_tree(root: Any, *, max_depth: int = 3, max_items: int = 80) -> list[dict[str, Any]]:
    """Flatten a pywinauto-like wrapper tree into stable, compact dictionaries."""

    if root is None:
        return []
    output: list[dict[str, Any]] = []
    queue: deque[tuple[Any, int, str]] = deque([(root, 0, "0")])
    while queue and len(output) < max(0, int(max_items)):
        node, depth, path = queue.popleft()
        item = _uia_item_from_node(node, depth=depth, path=path, index=len(output))
        if item is not None:
            output.append(item)
        if depth >= max(0, int(max_depth)):
            continue
        children = _safe_children(node)
        for child_index, child in enumerate(children[: max(0, int(max_items))]):
            queue.append((child, depth + 1, f"{path}.{child_index}"))
    return output


def _uia_item_from_node(node: Any, *, depth: int, path: str, index: int) -> dict[str, Any] | None:
    info = getattr(node, "element_info", None)
    name = _compact_text(_first_present(_call_or_value(getattr(node, "window_text", None)), getattr(info, "name", None)))
    control_type = _compact_text(getattr(info, "control_type", None), limit=80)
    automation_id = _compact_text(getattr(info, "automation_id", None), limit=120)
    class_name = _compact_text(getattr(info, "class_name", None), limit=120)
    rectangle = _rectangle_to_dict(_first_present(_call_or_value(getattr(node, "rectangle", None)), getattr(info, "rectangle", None)))
    if not any((name, control_type, automation_id, class_name)):
        return None
    item: dict[str, Any] = {
        "index": index,
        "depth": depth,
        "path": path,
        "name": name,
        "control_type": control_type,
    }
    if automation_id:
        item["automation_id"] = automation_id
    if class_name:
        item["class_name"] = class_name
    if rectangle:
        item["rect"] = rectangle
    selector_parts = []
    if control_type:
        selector_parts.append(f"control_type={control_type}")
    if automation_id:
        selector_parts.append(f"auto_id={automation_id}")
    elif name:
        selector_parts.append(f"name={name}")
    if selector_parts:
        item["selector"] = ";".join(selector_parts)
    return item


def _safe_children(node: Any) -> list[Any]:
    children_fn = getattr(node, "children", None)
    if callable(children_fn):
        try:
            children = children_fn()
            if isinstance(children, list):
                return children
            return list(children or [])
        except Exception:
            return []
    return []


def _call_or_value(value: Any) -> Any:
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _rectangle_to_dict(rectangle: Any) -> dict[str, int] | None:
    if rectangle is None:
        return None
    try:
        left = int(getattr(rectangle, "left"))
        top = int(getattr(rectangle, "top"))
        right = int(getattr(rectangle, "right"))
        bottom = int(getattr(rectangle, "bottom"))
    except Exception:
        return None
    width = max(0, right - left)
    height = max(0, bottom - top)
    return {"x": left, "y": top, "width": width, "height": height}


def _compact_text(value: Any, *, limit: int = 160) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _escape_title_fragment(value: str) -> str:
    import re

    return re.escape(value[:120])
