from desktop_agent.config import AgentConfig
from desktop_agent.windows_env import (
    DesktopEnvironment,
    MonitorSnapshot,
    Rect,
    TaskbarState,
    WindowSnapshot,
    detect_display_environment,
)


def _build_detected_environment() -> DesktopEnvironment:
    return DesktopEnvironment(
        platform="windows",
        virtual_bounds=Rect(0, 0, 3840, 1080),
        monitors=[
            MonitorSnapshot(
                device_name="DISPLAY1",
                is_primary=True,
                bounds=Rect(0, 0, 1920, 1080),
                work_area=Rect(0, 0, 1920, 1040),
            ),
            MonitorSnapshot(
                device_name="DISPLAY2",
                is_primary=False,
                bounds=Rect(1920, 0, 3840, 1080),
                work_area=Rect(1920, 0, 3840, 1040),
            ),
        ],
        current_monitor=MonitorSnapshot(
            device_name="DISPLAY1",
            is_primary=True,
            bounds=Rect(0, 0, 1920, 1080),
            work_area=Rect(0, 0, 1920, 1040),
        ),
        dpi_scale=1.25,
        taskbar=TaskbarState(position="bottom", auto_hide=False, occupies_work_area=True, rect=Rect(0, 1040, 1920, 1080)),
        foreground_window=WindowSnapshot(handle=1, title="Notepad", monitor_device_name="DISPLAY1"),
        visible_windows=[WindowSnapshot(handle=1, title="Notepad", monitor_device_name="DISPLAY1")],
    )


def test_detect_display_environment_applies_effective_overrides():
    config = AgentConfig(
        display_override_enabled=True,
        display_override_monitor_device_name="DISPLAY2",
        display_override_dpi_scale=1.5,
        display_override_work_area_left=2000,
        display_override_work_area_top=30,
        display_override_work_area_width=1600,
        display_override_work_area_height=900,
    )

    snapshot = detect_display_environment(config=config, detected_environment=_build_detected_environment())

    assert snapshot.detected.current_monitor.device_name == "DISPLAY1"
    assert snapshot.effective.current_monitor.device_name == "DISPLAY2"
    assert snapshot.effective.current_monitor.work_area.left == 2000
    assert snapshot.effective.current_monitor.work_area.top == 30
    assert snapshot.effective.current_monitor.work_area.width == 1600
    assert snapshot.effective.current_monitor.work_area.height == 900
    assert snapshot.effective.dpi_scale == 1.5
    assert snapshot.override.status == "override"
    assert snapshot.override.applied == ["monitor_device_name", "work_area", "dpi_scale"]


def test_detect_display_environment_falls_back_when_saved_monitor_is_missing():
    config = AgentConfig(
        display_override_enabled=True,
        display_override_monitor_device_name="MISSING_DISPLAY",
        display_override_dpi_scale=1.5,
        display_override_work_area_left=2000,
        display_override_work_area_top=30,
        display_override_work_area_width=1600,
        display_override_work_area_height=900,
    )

    snapshot = detect_display_environment(config=config, detected_environment=_build_detected_environment())

    assert snapshot.effective.current_monitor.device_name == "DISPLAY1"
    assert snapshot.effective.current_monitor.work_area.left == 0
    assert snapshot.effective.current_monitor.work_area.top == 0
    assert snapshot.effective.current_monitor.work_area.width == 1920
    assert snapshot.effective.current_monitor.work_area.height == 1040
    assert snapshot.effective.dpi_scale == 1.25
    assert snapshot.override.status == "invalid_override"
    assert snapshot.override.warnings
    assert "MISSING_DISPLAY" in snapshot.override.warnings[0]
    assert snapshot.override.applied == []


def test_detect_display_environment_is_read_only_off_windows():
    config = AgentConfig(display_override_enabled=True, display_override_dpi_scale=1.4)
    detected = DesktopEnvironment(platform="posix", virtual_bounds=Rect(0, 0, 0, 0))

    snapshot = detect_display_environment(config=config, detected_environment=detected)

    assert snapshot.override.status == "readonly"
    assert snapshot.override.editable is False
    assert snapshot.effective.platform == "posix"
