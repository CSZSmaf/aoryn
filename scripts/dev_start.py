from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib import error as url_error
from urllib import request as url_request


DEFAULT_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765
DEFAULT_BROWSER_PORT = 38991
DEFAULT_BROWSER_PROFILE = Path(".tmp") / "browser-runtime" / "browser-profile"
APP_TITLE = "Aoryn"


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    project_root: Path
    host: str
    dashboard_port: int
    browser_port: int
    ui_mode: str
    dashboard_command: list[str]
    browser_command: list[str] | None
    dashboard_url: str
    browser_url: str


@dataclass(frozen=True, slots=True)
class PortProbe:
    state: str
    detail: str = ""

    @property
    def is_free(self) -> bool:
        return self.state == "free"

    @property
    def is_aoryn(self) -> bool:
        return self.state == "aoryn"

    @property
    def is_occupied(self) -> bool:
        return self.state == "occupied"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the Aoryn source-mode development workbench.")
    parser.add_argument("--ui", choices=["shell", "web"], default="shell", help="UI mode to launch.")
    parser.add_argument("--port", type=int, default=DEFAULT_DASHBOARD_PORT, help="Dashboard HTTP port.")
    parser.add_argument(
        "--managed-browser-port",
        type=int,
        default=DEFAULT_BROWSER_PORT,
        help="Aoryn Browser Runtime HTTP port.",
    )
    parser.add_argument(
        "--no-managed-browser",
        action="store_true",
        help="Start only the main workbench and skip the managed browser runtime.",
    )
    parser.add_argument(
        "--no-browser-tab",
        action="store_true",
        help="Do not open a normal browser tab for the web dashboard.",
    )
    parser.add_argument("--config", type=Path, default=None, help="Optional config YAML path.")
    parser.add_argument(
        "--print-commands",
        action="store_true",
        help="Print the source-mode commands without starting GUI processes.",
    )
    return parser.parse_args(argv)


def build_launch_plan(args: argparse.Namespace, *, project_root: Path | None = None) -> LaunchPlan:
    root = (project_root or _project_root()).resolve()
    run_agent = root / "run_agent.py"
    run_browser = root / "run_browser.py"

    dashboard_command = [
        sys.executable,
        str(run_agent),
        "ui",
        "--host",
        DEFAULT_HOST,
        "--port",
        str(int(args.port)),
    ]
    if args.ui == "web":
        dashboard_command.append("--browser")
    if args.no_browser_tab:
        dashboard_command.append("--no-browser")
    if args.config is not None:
        dashboard_command.extend(["--config", str(args.config)])

    browser_command: list[str] | None = None
    if not args.no_managed_browser:
        browser_profile = root / DEFAULT_BROWSER_PROFILE
        browser_command = [
            sys.executable,
            str(run_browser),
            "--port",
            str(int(args.managed_browser_port)),
            "--profile-root",
            str(browser_profile),
        ]
        if args.config is not None:
            browser_command.extend(["--config-path", str(args.config)])

    return LaunchPlan(
        project_root=root,
        host=DEFAULT_HOST,
        dashboard_port=int(args.port),
        browser_port=int(args.managed_browser_port),
        ui_mode=str(args.ui),
        dashboard_command=dashboard_command,
        browser_command=browser_command,
        dashboard_url=f"http://{DEFAULT_HOST}:{int(args.port)}",
        browser_url=f"http://{DEFAULT_HOST}:{int(args.managed_browser_port)}",
    )


def run(argv: Sequence[str] | None = None, *, project_root: Path | None = None) -> int:
    args = parse_args(argv)
    plan = build_launch_plan(args, project_root=project_root)

    _print_header(plan)
    if args.print_commands:
        _print_commands(plan)
        return 0

    dashboard_probe = _probe_dashboard_port(plan.host, plan.dashboard_port)
    if dashboard_probe.is_aoryn:
        print(f"Reusing existing Aoryn dashboard at {plan.dashboard_url}.")
        return 0
    if dashboard_probe.is_occupied:
        print(
            f"Dashboard port {plan.dashboard_port} is already in use by another service. "
            f"Try --port {plan.dashboard_port + 1}. {dashboard_probe.detail}".strip(),
            file=sys.stderr,
        )
        return 2

    started: list[tuple[str, subprocess.Popen]] = []
    try:
        if plan.browser_command is not None:
            browser_process = _start_managed_browser(plan)
            if browser_process is not None:
                started.append(("Aoryn Browser Runtime", browser_process))

        dashboard_process = _start_process(plan.dashboard_command, cwd=plan.project_root)
        started.append(("Aoryn workbench", dashboard_process))
        print(f"Started Aoryn workbench (pid {dashboard_process.pid}).")
        print("Keep this terminal open while testing. Press Ctrl+C to stop source-mode processes.")
        return int(dashboard_process.wait() or 0)
    except KeyboardInterrupt:
        print("\nStopping Aoryn source-mode processes...")
        return 130
    finally:
        _stop_started_processes(started)


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _print_header(plan: LaunchPlan) -> None:
    print("Aoryn source development launcher")
    print(f"Dashboard: {plan.dashboard_url}")
    print(f"Browser Runtime: {plan.browser_url}")
    print(f"UI mode: {plan.ui_mode}")


def _print_commands(plan: LaunchPlan) -> None:
    if plan.browser_command is not None:
        print(f"Browser command: {_format_command(plan.browser_command)}")
    else:
        print("Browser command: <skipped>")
    print(f"Dashboard command: {_format_command(plan.dashboard_command)}")


def _format_command(command: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in command])


def _probe_dashboard_port(host: str, port: int) -> PortProbe:
    if not _tcp_port_open(host, port):
        return PortProbe("free")
    payload = _read_json(f"http://{host}:{port}/api/overview")
    if isinstance(payload, dict):
        meta = payload.get("meta")
        if isinstance(meta, dict) and str(meta.get("title") or "").strip() == APP_TITLE:
            return PortProbe("aoryn", "Aoryn dashboard responded to /api/overview.")
    return PortProbe("occupied", "The port is open but did not respond like an Aoryn dashboard.")


def _probe_browser_runtime_port(host: str, port: int) -> PortProbe:
    if not _tcp_port_open(host, port):
        return PortProbe("free")
    payload = _read_json(f"http://{host}:{port}/status")
    if isinstance(payload, dict) and (
        payload.get("runtime") == "aoryn_browser" or payload.get("managed_by") == "aoryn_browser"
    ):
        return PortProbe("aoryn", "Aoryn Browser Runtime responded to /status.")
    return PortProbe("occupied", "The port is open but did not respond like Aoryn Browser Runtime.")


def _read_json(url: str, *, timeout: float = 0.45) -> dict | None:
    try:
        with url_request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read(128 * 1024).decode("utf-8"))
    except (OSError, ValueError, url_error.URLError):
        return None


def _tcp_port_open(host: str, port: int, *, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _start_managed_browser(plan: LaunchPlan) -> subprocess.Popen | None:
    assert plan.browser_command is not None
    browser_probe = _probe_browser_runtime_port(plan.host, plan.browser_port)
    if browser_probe.is_aoryn:
        print(f"Reusing existing Aoryn Browser Runtime at {plan.browser_url}.")
        return None
    if browser_probe.is_occupied:
        print(
            f"Managed browser port {plan.browser_port} is already in use; "
            "continuing without starting a new managed browser.",
            file=sys.stderr,
        )
        return None

    qt_available, qt_detail = _qtwebengine_available(plan.project_root)
    if not qt_available:
        print(
            "Managed browser skipped because PySide6 QtWebEngine is unavailable. "
            f"{qt_detail}".strip(),
            file=sys.stderr,
        )
        return None

    process = _start_process(plan.browser_command, cwd=plan.project_root)
    time.sleep(0.75)
    if process.poll() is not None:
        print(
            "Managed browser exited during startup; continuing with the main workbench.",
            file=sys.stderr,
        )
        return None
    print(f"Started Aoryn Browser Runtime (pid {process.pid}).")
    return process


def _qtwebengine_available(project_root: Path) -> tuple[bool, str]:
    root_text = str(project_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    try:
        from desktop_agent import aoryn_browser
    except Exception as exc:  # pragma: no cover - import failures are environment-specific
        return False, str(exc)

    if getattr(aoryn_browser, "QApplication", None) is None:
        detail = getattr(aoryn_browser, "_QT_IMPORT_ERROR", None)
        return False, str(detail or "Install dependencies from requirements.txt.")
    return True, ""


def _start_process(command: Sequence[str], *, cwd: Path) -> subprocess.Popen:
    return subprocess.Popen([str(part) for part in command], cwd=str(cwd))


def _stop_started_processes(processes: list[tuple[str, subprocess.Popen]]) -> None:
    for label, process in reversed(processes):
        if process.poll() is not None:
            continue
        print(f"Stopping {label} (pid {process.pid})...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
