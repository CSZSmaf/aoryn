from desktop_agent.windows_uia import flatten_uia_tree


class _Rect:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class _Info:
    def __init__(self, *, name="", control_type="", automation_id="", class_name="", rectangle=None):
        self.name = name
        self.control_type = control_type
        self.automation_id = automation_id
        self.class_name = class_name
        self.rectangle = rectangle


class _Node:
    def __init__(self, text, info, children=None, rectangle=None):
        self.element_info = info
        self._text = text
        self._children = children or []
        self._rectangle = rectangle

    def window_text(self):
        return self._text

    def rectangle(self):
        return self._rectangle

    def children(self):
        return list(self._children)


def test_flatten_uia_tree_extracts_stable_control_metadata():
    ok_button = _Node(
        "OK",
        _Info(control_type="Button", automation_id="okButton", class_name="Button"),
        rectangle=_Rect(10, 20, 110, 52),
    )
    root = _Node(
        "Settings",
        _Info(control_type="Window", automation_id="settingsWindow"),
        [ok_button],
        rectangle=_Rect(0, 0, 400, 300),
    )

    tree = flatten_uia_tree(root, max_depth=2, max_items=10)

    assert tree[0]["name"] == "Settings"
    assert tree[0]["selector"] == "control_type=Window;auto_id=settingsWindow"
    assert tree[1]["name"] == "OK"
    assert tree[1]["control_type"] == "Button"
    assert tree[1]["automation_id"] == "okButton"
    assert tree[1]["rect"] == {"x": 10, "y": 20, "width": 100, "height": 32}
    assert tree[1]["selector"] == "control_type=Button;auto_id=okButton"
