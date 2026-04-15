from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from desktop_agent.config import AgentConfig
from desktop_agent.windows_env import (
    DesktopEnvironment,
    capture_desktop_environment,
    detect_display_environment,
)


class PerceptionError(RuntimeError):
    """Raised when screen capture fails."""


@dataclass(slots=True)
class ScreenInfo:
    width: int
    height: int
    environment: DesktopEnvironment | None = None
    detected_environment: DesktopEnvironment | None = None
    effective_environment: DesktopEnvironment | None = None


class ScreenCapture:
    """Capture the current desktop as an image."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config
        self.last_screen_info: ScreenInfo | None = None

    def capture(self, output_path: Path) -> ScreenInfo:
        try:
            import mss  # imported lazily to keep tests headless-friendly
            from PIL import Image
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise PerceptionError("ScreenCapture requires both mss and Pillow.") from exc

        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                shot = sct.grab(monitor)
                image = Image.frombytes("RGB", shot.size, shot.rgb)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                image.save(output_path)
                display_detection = detect_display_environment(
                    config=self.config,
                    detected_environment=capture_desktop_environment(),
                )
                self.last_screen_info = ScreenInfo(
                    width=image.width,
                    height=image.height,
                    environment=display_detection.effective,
                    detected_environment=display_detection.detected,
                    effective_environment=display_detection.effective,
                )
                return self.last_screen_info
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            raise PerceptionError(str(exc)) from exc


class MockCapture(ScreenCapture):
    """Generate a placeholder screenshot for tests and dry-run demonstrations."""

    _FALLBACK_PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+kv4QAAAAASUVORK5CYII="
    )

    def __init__(self, width: int = 1280, height: int = 720, config: AgentConfig | None = None) -> None:
        super().__init__(config=config)
        self.width = width
        self.height = height

    def capture(self, output_path: Path) -> ScreenInfo:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        display_detection = detect_display_environment(
            config=self.config,
            detected_environment=capture_desktop_environment(),
        )
        if self._capture_with_pillow(output_path):
            self.last_screen_info = ScreenInfo(
                width=self.width,
                height=self.height,
                environment=display_detection.effective,
                detected_environment=display_detection.detected,
                effective_environment=display_detection.effective,
            )
            return self.last_screen_info

        output_path.write_bytes(self._FALLBACK_PNG)
        self.last_screen_info = ScreenInfo(
            width=self.width,
            height=self.height,
            environment=display_detection.effective,
            detected_environment=display_detection.detected,
            effective_environment=display_detection.effective,
        )
        return self.last_screen_info

    def _capture_with_pillow(self, output_path: Path) -> bool:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ModuleNotFoundError:
            return False

        image = Image.new("RGB", (self.width, self.height), "white")
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                28,
            )
        except Exception:
            font = ImageFont.load_default()
        draw.rectangle((40, 40, self.width - 40, self.height - 40), outline="black", width=3)
        draw.text((70, 80), "Mock Desktop", fill="black", font=font)
        draw.text(
            (70, 140),
            "MockCapture generated this screenshot for tests and dry-run logs.",
            fill="black",
            font=font,
        )
        image.save(output_path)
        return True
