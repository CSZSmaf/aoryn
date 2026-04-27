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
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">
          <path d="M14.4 6.4L8.8 12l5.6 5.6" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M9.4 12H19" stroke="{color}" stroke-width="1.75" stroke-linecap="round"/>
        </svg>
    """,
    "forward": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">
          <path d="M9.6 6.4L15.2 12l-5.6 5.6" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M14.6 12H5" stroke="{color}" stroke-width="1.75" stroke-linecap="round"/>
        </svg>
    """,
    "reload": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">
          <path d="M17.1 8.2A6.3 6.3 0 1 0 18 13.3" stroke="{color}" stroke-width="1.72" stroke-linecap="round"/>
          <path d="M13.8 6.2H18.1V10.5" stroke="{color}" stroke-width="1.72" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    """,
    "home": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">
          <path d="M5.6 11.3L12 6.1L18.4 11.3" stroke="{color}" stroke-width="1.72" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M7.7 10.3V18H16.3V10.3" stroke="{color}" stroke-width="1.72" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M10.3 18V14.4H13.7V18" stroke="{color}" stroke-width="1.72" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    """,
    "add": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">
          <path d="M12 6.4V17.6" stroke="{color}" stroke-width="1.75" stroke-linecap="round"/>
          <path d="M6.4 12H17.6" stroke="{color}" stroke-width="1.75" stroke-linecap="round"/>
        </svg>
    """,
    "more": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="6.8" r="1.45" fill="{color}"/>
          <circle cx="12" cy="12" r="1.45" fill="{color}"/>
          <circle cx="12" cy="17.2" r="1.45" fill="{color}"/>
        </svg>
    """,
    "search": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">
          <circle cx="10.7" cy="10.7" r="5.7" stroke="{color}" stroke-width="1.65"/>
          <path d="M15.1 15.1L19 19" stroke="{color}" stroke-width="1.65" stroke-linecap="round"/>
        </svg>
    """,
    "spark": """
        <svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">
          <path d="M12 4.8L13.7 9.9L18.8 11.8L13.7 13.7L12 18.8L10.3 13.7L5.2 11.8L10.3 9.9L12 4.8Z" stroke="{color}" stroke-width="1.55" stroke-linejoin="round"/>
          <path d="M18.7 4.8L19.3 6.7L21.2 7.3L19.3 8L18.7 9.8L18 8L16.2 7.3L18 6.7L18.7 4.8Z" stroke="{color}" stroke-width="1.25" stroke-linejoin="round"/>
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
