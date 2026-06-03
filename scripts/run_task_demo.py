"""Run the three required live-demo desktop tasks.

This drives the real desktop executor. It opens Calculator, the browser,
Notepad, and optionally QQ.

Usage:
    python scripts/run_task_demo.py
    python scripts/run_task_demo.py 1 2
    python scripts/run_task_demo.py 3 --qq-group "项目演示群" --qq-message "今天的演示已准备好"

Environment fallback for task #3:
    AORYN_DEMO_QQ_GROUP
    AORYN_DEMO_QQ_MESSAGE
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow running directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from desktop_agent.controller import run_task  # noqa: E402


BASE_TASKS: dict[int, tuple[str, str]] = {
    1: ("计算器 1+1", "打开计算器计算1+1"),
    2: (
        "北京旅游攻略 -> 记事本",
        "打开浏览器搜索北京旅游攻略，阅读多个网页后总结，并把总结内容写在记事本上",
    ),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the three Aoryn live-demo tasks.")
    parser.add_argument("tasks", nargs="*", type=int, help="Task numbers to run: 1, 2, 3. Defaults to all.")
    parser.add_argument("--qq-group", default=os.environ.get("AORYN_DEMO_QQ_GROUP", ""), help="Target QQ group name.")
    parser.add_argument("--qq-message", default=os.environ.get("AORYN_DEMO_QQ_MESSAGE", ""), help="Message to send.")
    return parser


def _select_tasks(task_numbers: list[int], *, qq_group: str, qq_message: str) -> list[tuple[str, str]]:
    numbers = task_numbers or [1, 2, 3]
    selected: list[tuple[str, str]] = []
    for number in numbers:
        if number in BASE_TASKS:
            selected.append(BASE_TASKS[number])
        elif number == 3:
            group = qq_group.strip()
            message = qq_message.strip()
            if not group or not message:
                selected.append(
                    (
                        "QQ 群聊发送",
                        "打开QQ在群聊发送消息",
                    )
                )
            else:
                selected.append(
                    (
                        "QQ 群聊发送",
                        f"打开QQ在群聊“{group}”发送消息“{message}”",
                    )
                )
    return selected or [BASE_TASKS[1], BASE_TASKS[2]]


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    selected = _select_tasks(args.tasks, qq_group=args.qq_group, qq_message=args.qq_message)
    print("=" * 72)
    print(" Aoryn 桌面智能代理 - 三项演示任务")
    print(" 将操作真实桌面：计算器、浏览器、记事本；选择任务 3 时还会操作 QQ。")
    print("=" * 72)

    for ordinal, (label, task) in enumerate(selected, start=1):
        print(f"\n[{ordinal}/{len(selected)}] {label}")
        print(f"  指令：{task}")
        print("  执行中...")
        try:
            result = run_task(task, dry_run=False)
        except KeyboardInterrupt:
            print("  已被用户中断。")
            return 130
        except Exception as exc:  # pragma: no cover - runtime dependent
            print(f"  运行出错：{exc}")
            continue

        answer = (result.answer or "").strip()
        if answer:
            print("  ---- Agent 回复 ----")
            for line in answer.splitlines():
                print(f"  {line}")
        else:
            status = "完成" if result.completed else (result.error or "未完成")
            print(f"  结果：{status}")
        time.sleep(1.2)

    print("\n演示任务执行完毕。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
