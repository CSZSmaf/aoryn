from __future__ import annotations

try:  # pragma: no cover - GUI runtime availability depends on environment
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QTabBar, QWidget

    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - GUI runtime availability depends on environment
    Qt = object  # type: ignore[assignment]
    QFrame = object  # type: ignore[assignment]
    QHBoxLayout = object  # type: ignore[assignment]
    QSizePolicy = object  # type: ignore[assignment]
    QTabBar = object  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]
    _QT_IMPORT_ERROR = exc


if _QT_IMPORT_ERROR is None:

    class BrowserTopChrome(QFrame):
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setObjectName("TopChromeBar")

            outer = QHBoxLayout(self)
            outer.setContentsMargins(8, 6, 8, 4)
            outer.setSpacing(8)

            self.nav_section = QFrame(self)
            self.nav_section.setObjectName("TopChromeSection")
            self.nav_layout = QHBoxLayout(self.nav_section)
            self.nav_layout.setContentsMargins(0, 0, 0, 0)
            self.nav_layout.setSpacing(2)
            outer.addWidget(self.nav_section, 0)

            self.address_section = QFrame(self)
            self.address_section.setObjectName("TopChromeAddressShell")
            self.address_layout = QHBoxLayout(self.address_section)
            self.address_layout.setContentsMargins(0, 0, 0, 0)
            self.address_layout.setSpacing(0)
            self.address_section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            outer.addWidget(self.address_section, 1)

            self.action_section = QFrame(self)
            self.action_section.setObjectName("TopChromeSection")
            self.action_layout = QHBoxLayout(self.action_section)
            self.action_layout.setContentsMargins(0, 0, 0, 0)
            self.action_layout.setSpacing(2)
            outer.addWidget(self.action_section, 0)

        def add_navigation_widget(self, widget: QWidget) -> None:
            self.nav_layout.addWidget(widget)

        def set_address_widget(self, widget: QWidget) -> None:
            self.address_layout.addWidget(widget)

        def add_action_widget(self, widget: QWidget) -> None:
            self.action_layout.addWidget(widget)


    class BrowserTabStrip(QTabBar):
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setObjectName("BrowserTabStrip")
            self.setDocumentMode(True)
            self.setDrawBase(False)
            self.setExpanding(False)
            self.setMovable(False)
            self.setUsesScrollButtons(True)
            self.setTabsClosable(True)
            self.setElideMode(Qt.TextElideMode.ElideRight)


else:

    class BrowserTopChrome(object):  # type: ignore[override]
        pass


    class BrowserTabStrip(object):  # type: ignore[override]
        pass
