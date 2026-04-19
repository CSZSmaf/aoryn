from __future__ import annotations

from functools import lru_cache

try:  # pragma: no cover - GUI runtime availability depends on environment
    from PySide6.QtGui import QIcon, QPixmap

    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - GUI runtime availability depends on environment
    QIcon = object  # type: ignore[assignment]
    QPixmap = object  # type: ignore[assignment]
    _QT_IMPORT_ERROR = exc


_ICON_TEMPLATES = {
    "back": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 20 20" fill="none">
          <path d="M11.8 4.8L6.3 10l5.5 5.2" stroke="{color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M7.1 10H14.7" stroke="{color}" stroke-width="1.9" stroke-linecap="round"/>
        </svg>
    """,
    "forward": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 20 20" fill="none">
          <path d="M8.2 4.8L13.7 10l-5.5 5.2" stroke="{color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M12.9 10H5.3" stroke="{color}" stroke-width="1.9" stroke-linecap="round"/>
        </svg>
    """,
    "reload": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 20 20" fill="none">
          <path d="M14.6 6.8A5.8 5.8 0 1 0 15.3 12" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
          <path d="M11.9 4.9H15.8V8.8" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    """,
    "home": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 20 20" fill="none">
          <path d="M4.7 9.1L10 4.6l5.3 4.5" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M6.2 8.2V15h7.6V8.2" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    """,
    "add": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 20 20" fill="none">
          <path d="M10 4.8V15.2" stroke="{color}" stroke-width="1.9" stroke-linecap="round"/>
          <path d="M4.8 10H15.2" stroke="{color}" stroke-width="1.9" stroke-linecap="round"/>
        </svg>
    """,
    "more": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 20 20" fill="none">
          <circle cx="5" cy="10" r="1.35" fill="{color}"/>
          <circle cx="10" cy="10" r="1.35" fill="{color}"/>
          <circle cx="15" cy="10" r="1.35" fill="{color}"/>
        </svg>
    """,
    "window": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 64 64" fill="none">
          <rect x="6" y="6" width="52" height="52" rx="16" fill="#244a9b"/>
          <path d="M18 48L31.5 16L45 48" stroke="#ffffff" stroke-width="5.8" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M24.5 35.5H39.5" stroke="#ffffff" stroke-width="5.2" stroke-linecap="round"/>
        </svg>
    """,
}


if _QT_IMPORT_ERROR is None:

    def _icon_from_svg(svg: str) -> QIcon:
        pixmap = QPixmap()
        if not pixmap.loadFromData(svg.encode("utf-8"), "SVG"):
            return QIcon()
        return QIcon(pixmap)


    @lru_cache(maxsize=32)
    def browser_chrome_icon(name: str, color: str = "#273142", size: int = 20) -> QIcon:
        template = _ICON_TEMPLATES.get(name)
        if template is None:
            return QIcon()
        return _icon_from_svg(template.format(color=color, size=size))


    @lru_cache(maxsize=4)
    def browser_window_icon(size: int = 64) -> QIcon:
        return _icon_from_svg(_ICON_TEMPLATES["window"].format(size=size))


else:

    def browser_chrome_icon(name: str, color: str = "#273142", size: int = 20) -> QIcon:  # type: ignore[misc]
        return QIcon()


    def browser_window_icon(size: int = 64) -> QIcon:  # type: ignore[misc]
        return QIcon()
