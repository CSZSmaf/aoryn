from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop_agent.config import AgentConfig


@dataclass(slots=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(slots=True)
class MonitorSnapshot:
    device_name: str
    is_primary: bool
    bounds: Rect
    work_area: Rect

    def to_dict(self) -> dict[str, object]:
        return {
            "device_name": self.device_name,
            "is_primary": self.is_primary,
            "bounds": self.bounds.to_dict(),
            "work_area": self.work_area.to_dict(),
        }


@dataclass(slots=True)
class TaskbarState:
    position: str | None = None
    auto_hide: bool = False
    occupies_work_area: bool = False
    rect: Rect | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "position": self.position,
            "auto_hide": self.auto_hide,
            "occupies_work_area": self.occupies_work_area,
            "rect": self.rect.to_dict() if self.rect else None,
        }


@dataclass(slots=True)
class WindowSnapshot:
    handle: int
    title: str
    class_name: str | None = None
    pid: int | None = None
    process_name: str | None = None
    rect: Rect | None = None
    is_visible: bool = True
    is_minimized: bool = False
    is_maximized: bool = False
    monitor_device_name: str | None = None

    def matches(self, text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return False
        haystacks = [self.title.lower()]
        if self.class_name:
            haystacks.append(self.class_name.lower())
        if self.process_name:
            haystacks.append(self.process_name.lower())
        return any(lowered in item for item in haystacks if item)

    def to_dict(self) -> dict[str, object]:
        return {
            "handle": self.handle,
            "title": self.title,
            "class_name": self.class_name,
            "pid": self.pid,
            "process_name": self.process_name,
            "rect": self.rect.to_dict() if self.rect else None,
            "is_visible": self.is_visible,
            "is_minimized": self.is_minimized,
            "is_maximized": self.is_maximized,
            "monitor_device_name": self.monitor_device_name,
        }


@dataclass(slots=True)
class DesktopEnvironment:
    platform: str
    virtual_bounds: Rect
    monitors: list[MonitorSnapshot] = field(default_factory=list)
    current_monitor: MonitorSnapshot | None = None
    dpi_scale: float = 1.0
    taskbar: TaskbarState | None = None
    foreground_window: WindowSnapshot | None = None
    visible_windows: list[WindowSnapshot] = field(default_factory=list)
    captured_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "virtual_bounds": self.virtual_bounds.to_dict(),
            "monitors": [item.to_dict() for item in self.monitors],
            "current_monitor": self.current_monitor.to_dict() if self.current_monitor else None,
            "dpi_scale": self.dpi_scale,
            "taskbar": self.taskbar.to_dict() if self.taskbar else None,
            "foreground_window": self.foreground_window.to_dict() if self.foreground_window else None,
            "visible_windows": [item.to_dict() for item in self.visible_windows],
            "captured_at": self.captured_at,
        }


@dataclass(slots=True)
class DisplayOverrideState:
    enabled: bool
    editable: bool
    status: str
    monitor_device_name: str | None = None
    dpi_scale: float | None = None
    work_area: Rect | None = None
    applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "editable": self.editable,
            "status": self.status,
            "monitor_device_name": self.monitor_device_name,
            "dpi_scale": self.dpi_scale,
            "work_area": self.work_area.to_dict() if self.work_area else None,
            "applied": list(self.applied),
            "warnings": list(self.warnings),
            "message": self.message,
        }


@dataclass(slots=True)
class DisplayDetectionResult:
    detected: DesktopEnvironment
    effective: DesktopEnvironment
    override: DisplayOverrideState
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        return {
            "detected": self.detected.to_dict(),
            "effective": self.effective.to_dict(),
            "override": self.override.to_dict(),
            "checked_at": self.checked_at,
        }


def capture_desktop_environment() -> DesktopEnvironment:
    if os.name != "nt":
        return DesktopEnvironment(
            platform=os.name,
            virtual_bounds=Rect(0, 0, 0, 0),
        )
    return _capture_windows_environment()


def capture_effective_desktop_environment(config: AgentConfig | None = None) -> DesktopEnvironment:
    return detect_display_environment(config=config).effective


def detect_display_environment(
    config: AgentConfig | None = None,
    *,
    detected_environment: DesktopEnvironment | None = None,
) -> DisplayDetectionResult:
    detected = _clone_environment(detected_environment or capture_desktop_environment())
    effective, override = _apply_display_overrides(detected, config=config)
    return DisplayDetectionResult(
        detected=detected,
        effective=effective,
        override=override,
    )


def find_window(environment: DesktopEnvironment | None, query: str) -> WindowSnapshot | None:
    if environment is None:
        return None
    for item in environment.visible_windows:
        if item.matches(query):
            return item
    foreground = environment.foreground_window
    if foreground and foreground.matches(query):
        return foreground
    return None


def focus_window(handle: int) -> bool:
    user32 = _user32()
    if user32 is None or not handle:
        return False
    if user32.IsIconic(handle):
        user32.ShowWindow(handle, 9)
    user32.ShowWindow(handle, 5)
    return bool(user32.SetForegroundWindow(handle))


def maximize_window(handle: int) -> bool:
    user32 = _user32()
    if user32 is None or not handle:
        return False
    return bool(user32.ShowWindow(handle, 3))


def minimize_window(handle: int) -> bool:
    user32 = _user32()
    if user32 is None or not handle:
        return False
    return bool(user32.ShowWindow(handle, 6))


def close_window(handle: int) -> bool:
    user32 = _user32()
    if user32 is None or not handle:
        return False
    return bool(user32.PostMessageW(handle, 0x0010, 0, 0))


def move_resize_window(handle: int, rect: Rect) -> bool:
    user32 = _user32()
    if user32 is None or not handle:
        return False
    return bool(user32.MoveWindow(handle, rect.left, rect.top, rect.width, rect.height, True))


def launch_app_by_name(target: str) -> bool:
    if os.name != "nt":
        return False
    cleaned = (target or "").strip()
    if not cleaned:
        return False
    try:
        result = ctypes.windll.shell32.ShellExecuteW(None, "open", cleaned, None, None, 1)
        return int(result) > 32
    except Exception:
        return False


def wait_for_window(query: str, *, timeout_seconds: float = 2.5, poll_interval: float = 0.1) -> WindowSnapshot | None:
    deadline = time.time() + max(0.1, timeout_seconds)
    while time.time() < deadline:
        window = find_window(capture_desktop_environment(), query)
        if window is not None:
            return window
        time.sleep(poll_interval)
    return None


def preferred_work_area(environment: DesktopEnvironment | None) -> Rect | None:
    if environment is None:
        return None
    if environment.current_monitor is not None:
        return environment.current_monitor.work_area
    if environment.monitors:
        primary = next((item for item in environment.monitors if item.is_primary), None)
        return (primary or environment.monitors[0]).work_area
    return None


def _apply_display_overrides(
    detected: DesktopEnvironment,
    *,
    config: AgentConfig | None = None,
) -> tuple[DesktopEnvironment, DisplayOverrideState]:
    effective = _clone_environment(detected)
    enabled = bool(getattr(config, "display_override_enabled", False))
    editable = detected.platform == "windows"
    override = DisplayOverrideState(
        enabled=enabled,
        editable=editable,
        status="auto",
        monitor_device_name=_optional_text(getattr(config, "display_override_monitor_device_name", None)),
        dpi_scale=_optional_positive_float(getattr(config, "display_override_dpi_scale", None)),
    )
    override.work_area, work_area_warning = _optional_work_area_override(config)
    if work_area_warning:
        override.warnings.append(work_area_warning)

    if not editable:
        override.status = "readonly"
        override.message = "Display overrides are only available on Windows."
        return effective, override

    if not enabled:
        override.status = "auto"
        override.message = "Using automatic display detection."
        return effective, override

    target_monitor = effective.current_monitor
    requested_monitor = override.monitor_device_name
    if requested_monitor:
        matched_monitor = next((item for item in effective.monitors if item.device_name == requested_monitor), None)
        if matched_monitor is None:
            override.warnings.append(
                f"The saved monitor `{requested_monitor}` is no longer available. Falling back to automatic detection."
            )
            override.status = "invalid_override"
            override.message = "The saved monitor override is invalid, so automatic detection is being used."
            return effective, override
        else:
            target_monitor = _clone_monitor(matched_monitor)
            effective.current_monitor = target_monitor
            override.applied.append("monitor_device_name")

    if override.work_area is not None:
        if target_monitor is None:
            override.warnings.append("A work-area override was provided, but no current monitor is available.")
        else:
            target_monitor.work_area = _clone_rect(override.work_area)
            effective.current_monitor = target_monitor
            override.applied.append("work_area")

    if override.dpi_scale is not None:
        effective.dpi_scale = override.dpi_scale
        override.applied.append("dpi_scale")

    if override.warnings:
        override.status = "invalid_override"
        override.message = "Some saved display overrides are invalid, so automatic detection is being used where needed."
    elif override.applied:
        override.status = "override"
        override.message = "Manual display overrides are active for planning and positioning."
    else:
        override.status = "auto"
        override.message = "Manual display correction is enabled, but no override values are currently applied."
    return effective, override


def _optional_work_area_override(config: AgentConfig | None) -> tuple[Rect | None, str | None]:
    if config is None:
        return None, None
    raw_values = (
        getattr(config, "display_override_work_area_left", None),
        getattr(config, "display_override_work_area_top", None),
        getattr(config, "display_override_work_area_width", None),
        getattr(config, "display_override_work_area_height", None),
    )
    present = [value is not None for value in raw_values]
    if any(present) and not all(present):
        return None, "Manual work-area override is incomplete."
    if not any(present):
        return None, None

    try:
        left, top, width, height = (int(value) for value in raw_values)
    except (TypeError, ValueError):
        return None, "Manual work-area override contains non-numeric values."

    if width <= 0 or height <= 0:
        return None, "Manual work-area override must use positive width and height."
    return Rect(left, top, left + width, top + height), None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_positive_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return round(number, 4)


def _clone_environment(environment: DesktopEnvironment) -> DesktopEnvironment:
    return DesktopEnvironment(
        platform=environment.platform,
        virtual_bounds=_clone_rect(environment.virtual_bounds),
        monitors=[_clone_monitor(item) for item in environment.monitors],
        current_monitor=_clone_monitor(environment.current_monitor),
        dpi_scale=environment.dpi_scale,
        taskbar=_clone_taskbar(environment.taskbar),
        foreground_window=_clone_window(environment.foreground_window),
        visible_windows=[_clone_window(item) for item in environment.visible_windows],
        captured_at=environment.captured_at,
    )


def _clone_monitor(monitor: MonitorSnapshot | None) -> MonitorSnapshot | None:
    if monitor is None:
        return None
    return MonitorSnapshot(
        device_name=monitor.device_name,
        is_primary=monitor.is_primary,
        bounds=_clone_rect(monitor.bounds),
        work_area=_clone_rect(monitor.work_area),
    )


def _clone_taskbar(taskbar: TaskbarState | None) -> TaskbarState | None:
    if taskbar is None:
        return None
    return TaskbarState(
        position=taskbar.position,
        auto_hide=taskbar.auto_hide,
        occupies_work_area=taskbar.occupies_work_area,
        rect=_clone_rect(taskbar.rect),
    )


def _clone_window(window: WindowSnapshot | None) -> WindowSnapshot | None:
    if window is None:
        return None
    return WindowSnapshot(
        handle=window.handle,
        title=window.title,
        class_name=window.class_name,
        pid=window.pid,
        process_name=window.process_name,
        rect=_clone_rect(window.rect),
        is_visible=window.is_visible,
        is_minimized=window.is_minimized,
        is_maximized=window.is_maximized,
        monitor_device_name=window.monitor_device_name,
    )


def _clone_rect(rect: Rect | None) -> Rect | None:
    if rect is None:
        return None
    return Rect(rect.left, rect.top, rect.right, rect.bottom)


def _capture_windows_environment() -> DesktopEnvironment:
    user32 = _user32()
    if user32 is None:
        return DesktopEnvironment(platform="windows", virtual_bounds=Rect(0, 0, 0, 0))

    _set_dpi_awareness(user32)
    virtual_bounds = Rect(
        user32.GetSystemMetrics(76),
        user32.GetSystemMetrics(77),
        user32.GetSystemMetrics(76) + user32.GetSystemMetrics(78),
        user32.GetSystemMetrics(77) + user32.GetSystemMetrics(79),
    )
    monitors = _enumerate_monitors(user32)
    foreground = _capture_window(user32.GetForegroundWindow(), user32, monitors)
    current_monitor = _pick_current_monitor(monitors, foreground)
    return DesktopEnvironment(
        platform="windows",
        virtual_bounds=virtual_bounds,
        monitors=monitors,
        current_monitor=current_monitor,
        dpi_scale=_read_dpi_scale(user32),
        taskbar=_read_taskbar_state(user32, current_monitor),
        foreground_window=foreground,
        visible_windows=_enumerate_windows(user32, monitors),
    )


def _pick_current_monitor(monitors: list[MonitorSnapshot], foreground: WindowSnapshot | None) -> MonitorSnapshot | None:
    if not monitors:
        return None
    if foreground and foreground.monitor_device_name:
        for item in monitors:
            if item.device_name == foreground.monitor_device_name:
                return item
    primary = next((item for item in monitors if item.is_primary), None)
    return primary or monitors[0]


def _enumerate_monitors(user32) -> list[MonitorSnapshot]:
    monitors: list[MonitorSnapshot] = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    monitor_enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)

    def callback(hmonitor, hdc, lprc, lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            monitors.append(
                MonitorSnapshot(
                    device_name=str(info.szDevice).strip(),
                    is_primary=bool(info.dwFlags & 1),
                    bounds=Rect(info.rcMonitor.left, info.rcMonitor.top, info.rcMonitor.right, info.rcMonitor.bottom),
                    work_area=Rect(info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom),
                )
            )
        return True

    user32.EnumDisplayMonitors(0, 0, monitor_enum_proc(callback), 0)
    return monitors


def _enumerate_windows(user32, monitors: list[MonitorSnapshot]) -> list[WindowSnapshot]:
    windows: list[WindowSnapshot] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, lparam):
        snapshot = _capture_window(hwnd, user32, monitors)
        if snapshot and snapshot.title:
            windows.append(snapshot)
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return windows


def _capture_window(hwnd: int, user32, monitors: list[MonitorSnapshot]) -> WindowSnapshot | None:
    if not hwnd:
        return None
    title = _window_text(hwnd, user32)
    class_name = _class_name(hwnd, user32)
    if not title and class_name in {"Shell_TrayWnd", "Progman"}:
        return None

    rect = _window_rect(hwnd, user32)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    monitor_name = _monitor_name_for_rect(rect, monitors)
    return WindowSnapshot(
        handle=int(hwnd),
        title=title,
        class_name=class_name or None,
        pid=int(pid.value) if pid.value else None,
        process_name=_process_name_for_pid(int(pid.value)) if pid.value else None,
        rect=rect,
        is_visible=bool(user32.IsWindowVisible(hwnd)),
        is_minimized=bool(user32.IsIconic(hwnd)),
        is_maximized=bool(user32.IsZoomed(hwnd)),
        monitor_device_name=monitor_name,
    )


def _window_text(hwnd: int, user32) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _class_name(hwnd: int, user32) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _process_name_for_pid(pid: int) -> str | None:
    if not pid:
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        process_handle = kernel32.OpenProcess(0x1000, False, pid)
        if not process_handle:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if kernel32.QueryFullProcessImageNameW(process_handle, 0, buffer, ctypes.byref(size)):
                return Path(buffer.value).name or None
        finally:
            kernel32.CloseHandle(process_handle)
    except Exception:
        return None
    return None


def _window_rect(hwnd: int, user32) -> Rect:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return Rect(0, 0, 0, 0)
    return Rect(rect.left, rect.top, rect.right, rect.bottom)


def _monitor_name_for_rect(rect: Rect | None, monitors: list[MonitorSnapshot]) -> str | None:
    if rect is None:
        return None
    center_x = rect.left + rect.width // 2
    center_y = rect.top + rect.height // 2
    for item in monitors:
        if item.bounds.left <= center_x < item.bounds.right and item.bounds.top <= center_y < item.bounds.bottom:
            return item.device_name
    return None


def _read_taskbar_state(user32, current_monitor: MonitorSnapshot | None) -> TaskbarState | None:
    taskbar_hwnd = user32.FindWindowW("Shell_TrayWnd", None)
    if not taskbar_hwnd:
        return None
    rect = _window_rect(taskbar_hwnd, user32)
    auto_hide = _taskbar_auto_hide()
    position = _taskbar_position(rect, current_monitor)
    occupies = not auto_hide
    return TaskbarState(position=position, auto_hide=auto_hide, occupies_work_area=occupies, rect=rect)


def _taskbar_auto_hide() -> bool:
    try:
        shell32 = ctypes.windll.shell32
        state = shell32.SHAppBarMessage(0x00000004, ctypes.byref(_appbar_data()))
        return bool(state & 0x0000001)
    except Exception:
        return False


def _appbar_data():
    class APPBARDATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uCallbackMessage", wintypes.UINT),
            ("uEdge", wintypes.UINT),
            ("rc", wintypes.RECT),
            ("lParam", wintypes.LPARAM),
        ]

    data = APPBARDATA()
    data.cbSize = ctypes.sizeof(APPBARDATA)
    return data


def _taskbar_position(rect: Rect, current_monitor: MonitorSnapshot | None) -> str:
    bounds = current_monitor.bounds if current_monitor is not None else None
    if bounds is None:
        if rect.width >= rect.height:
            return "top" if rect.top <= 0 else "bottom"
        return "left" if rect.left <= 0 else "right"
    if rect.top <= bounds.top and rect.width >= bounds.width // 2:
        return "top"
    if rect.bottom >= bounds.bottom and rect.width >= bounds.width // 2:
        return "bottom"
    if rect.left <= bounds.left:
        return "left"
    return "right"


def _read_dpi_scale(user32) -> float:
    try:
        hdc = user32.GetDC(0)
        gdi32 = ctypes.windll.gdi32
        dpi_x = gdi32.GetDeviceCaps(hdc, 88)
        user32.ReleaseDC(0, hdc)
        if dpi_x:
            return round(float(dpi_x) / 96.0, 4)
    except Exception:
        pass
    return 1.0


def _set_dpi_awareness(user32) -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        return


def _user32():
    try:
        return ctypes.windll.user32
    except Exception:
        return None
