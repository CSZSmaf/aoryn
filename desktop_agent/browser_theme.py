from __future__ import annotations

BROWSER_CHROME_STYLESHEET = """
QMainWindow {
    background: #f1f3f4;
}
QWidget#BrowserChromeRoot {
    background: #f1f3f4;
}
QFrame#TopChromeBar {
    background: transparent;
}
QFrame#TopChromeAddressShell,
QFrame#BrowserContentShell {
    background: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.08);
}
QFrame#TopChromeSection {
    background: transparent;
    border: 0;
}
QFrame#TopChromeAddressShell {
    border-radius: 18px;
    background: #ffffff;
    border-color: #dfe3e7;
    min-height: 36px;
    max-height: 36px;
}
QFrame#BrowserTabStripShell {
    background: transparent;
    border: 0;
    border-radius: 0;
    border-bottom: 0;
}
QFrame#BrowserContentShell {
    border-radius: 12px;
    border-color: #e3e7ec;
}
QToolButton#ChromeNavButton,
QToolButton#TabActionButton,
QToolButton#BrowserMenuButton,
QToolButton#AssistantToggleButton,
QToolButton#SetupToggleButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 14px;
    color: #273142;
    min-width: 24px;
    min-height: 24px;
    padding: 2px 6px;
    font: 600 12px "Segoe UI Variable Text";
}
QToolButton#ChromeNavButton:hover,
QToolButton#TabActionButton:hover,
QToolButton#BrowserMenuButton:hover,
QToolButton#AssistantToggleButton:hover,
QToolButton#SetupToggleButton:hover {
    background: rgba(15, 23, 42, 0.05);
    border-color: transparent;
}
QToolButton#ChromeNavButton:pressed,
QToolButton#TabActionButton:pressed,
QToolButton#BrowserMenuButton:pressed,
QToolButton#AssistantToggleButton:pressed,
QToolButton#SetupToggleButton:pressed {
    background: rgba(15, 23, 42, 0.08);
}
QToolButton#TabActionButton,
QToolButton#BrowserMenuButton {
    min-width: 28px;
    min-height: 28px;
}
QToolButton#AssistantToggleButton {
    min-width: 34px;
    min-height: 26px;
    padding: 2px 8px;
    color: #1d4ed8;
    font: 600 11px "Segoe UI Variable Text";
}
QToolButton#AssistantToggleButton:checked {
    background: rgba(29, 78, 216, 0.10);
    border-color: transparent;
}
QToolButton#BrowserMenuButton::menu-indicator {
    image: none;
    width: 0;
}
QLineEdit#AddressBar {
    background: transparent;
    border: 0;
    color: #18212f;
    min-height: 34px;
    max-height: 34px;
    padding: 0 14px;
    selection-background-color: rgba(29, 78, 216, 0.18);
    font: 13px "Segoe UI Variable Text";
}
QLineEdit#AddressBar::placeholder {
    color: #8d99aa;
}
QTabWidget::pane {
    border: 0;
    background: transparent;
}
QTabBar#BrowserTabStrip {
    background: transparent;
}
QTabBar#BrowserTabStrip::tab {
    background: rgba(241, 243, 244, 0.98);
    color: #5e6879;
    border: 1px solid #e3e7ec;
    border-bottom-color: #e3e7ec;
    border-radius: 10px 10px 0 0;
    padding: 6px 12px;
    margin: 0 4px 0 0;
    min-width: 120px;
    max-width: 220px;
    min-height: 28px;
    font: 600 12px "Segoe UI Variable Text";
}
QTabBar#BrowserTabStrip::tab:selected {
    background: #ffffff;
    color: #16202e;
    border-color: #e3e7ec;
    border-bottom-color: #ffffff;
}
QTabBar#BrowserTabStrip::tab:hover:!selected {
    background: rgba(248, 250, 252, 1);
    color: #16202e;
}
QTabBar#BrowserTabStrip::close-button {
    subcontrol-position: right;
    margin-left: 6px;
}
QMenu {
    background: rgba(255, 255, 255, 0.99);
    border: 1px solid rgba(15, 23, 42, 0.08);
    border-radius: 12px;
    padding: 6px;
}
QMenu::item {
    padding: 9px 12px;
    border-radius: 8px;
    color: #16202e;
}
QMenu::item:selected {
    background: rgba(29, 78, 216, 0.08);
    color: #1d4ed8;
}
QDockWidget#AssistantDock {
    border: 0;
}
QWidget#AssistantPanel {
    background: #f6f8fb;
    border-left: 1px solid rgba(15, 23, 42, 0.08);
}
QLabel#AssistantBadge {
    background: rgba(15, 23, 42, 0.06);
    color: #16202e;
    border-radius: 999px;
    padding: 4px 9px;
    font: 700 11px "Segoe UI Variable Text";
    max-width: 48px;
}
QLabel#AssistantHeading {
    color: #16202e;
    font: 600 16px "Segoe UI Variable";
}
QLabel#AssistantSubheading {
    color: #627084;
    font: 12px "Segoe UI Variable Text";
}
QLabel#AssistantStatus {
    color: #4a5566;
    background: rgba(255, 255, 255, 0.98);
    border: 1px solid rgba(15, 23, 42, 0.08);
    border-radius: 12px;
    padding: 10px 12px;
    font: 12px "Segoe UI Variable Text";
}
QFrame#AssistantContextCard {
    background: rgba(255, 255, 255, 0.99);
    border: 1px solid rgba(15, 23, 42, 0.08);
    border-radius: 14px;
}
QLabel#AssistantContextTitle {
    color: #16202e;
    font: 600 14px "Segoe UI Variable Text";
}
QLabel#AssistantContextUrl {
    color: #627084;
    font: 12px "Segoe UI Variable Text";
}
QPushButton#AssistantChip {
    background: rgba(255, 255, 255, 0.98);
    border: 1px solid rgba(15, 23, 42, 0.08);
    border-radius: 999px;
    color: #334155;
    padding: 7px 10px;
    font: 600 12px "Segoe UI Variable Text";
}
QPushButton#AssistantChip:hover {
    background: rgba(29, 78, 216, 0.08);
    border-color: rgba(29, 78, 216, 0.16);
    color: #1d4ed8;
}
QTextEdit#AssistantPrompt,
QTextEdit#AssistantResponse {
    background: rgba(255, 255, 255, 0.99);
    border: 1px solid rgba(15, 23, 42, 0.08);
    border-radius: 14px;
    padding: 10px 12px;
    color: #16202e;
    font: 13px "Segoe UI Variable Text";
}
QTextEdit#AssistantResponse {
    background: rgba(248, 250, 252, 0.98);
}
QTextEdit#AssistantPrompt:focus {
    border-color: rgba(29, 78, 216, 0.54);
}
QPushButton#AssistantPrimaryButton {
    background: #16202e;
    color: #ffffff;
    border: 0;
    border-radius: 14px;
    padding: 11px 14px;
    font: 600 13px "Segoe UI Variable Text";
}
QPushButton#AssistantPrimaryButton:hover {
    background: #233248;
}
QPushButton#AssistantSecondaryButton {
    background: rgba(255, 255, 255, 0.99);
    color: #334155;
    border: 1px solid rgba(15, 23, 42, 0.08);
    border-radius: 14px;
    padding: 10px 14px;
    font: 600 12px "Segoe UI Variable Text";
}
QPushButton#AssistantSecondaryButton:hover {
    background: rgba(241, 245, 249, 0.98);
    border-color: rgba(15, 23, 42, 0.14);
}
QDialog {
    background: #f6f8fb;
}
QLabel#AssistantSetupTitle {
    color: #16202e;
    font: 600 21px "Segoe UI Variable";
}
QLabel#AssistantSetupSubtitle,
QLabel#AssistantSetupStatus,
QLabel#AssistantSetupPaths {
    color: #627084;
    font: 12px "Segoe UI Variable Text";
}
QDialog QLineEdit,
QDialog QComboBox {
    min-height: 36px;
    border-radius: 12px;
    border: 1px solid rgba(15, 23, 42, 0.08);
    background: rgba(255, 255, 255, 0.99);
    padding: 6px 10px;
    color: #16202e;
}
QDialog QLineEdit:focus,
QDialog QComboBox:focus {
    border-color: rgba(29, 78, 216, 0.54);
}
QDialog QCheckBox {
    color: #334155;
    spacing: 8px;
}
QDialog QPushButton {
    min-height: 34px;
    border-radius: 12px;
    padding: 8px 14px;
    font: 600 12px "Segoe UI Variable Text";
}
QDialogButtonBox QPushButton {
    background: rgba(255, 255, 255, 0.98);
    border: 1px solid rgba(15, 23, 42, 0.08);
    color: #334155;
}
QDialogButtonBox QPushButton:hover {
    background: rgba(241, 245, 249, 0.98);
    border-color: rgba(15, 23, 42, 0.14);
}
"""
