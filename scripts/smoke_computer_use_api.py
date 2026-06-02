from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from desktop_agent.config import AgentConfig
from desktop_agent.planner import OpenAIComputerUsePlanner, PlannerError


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test OpenAI computer use planning without executing actions.")
    parser.add_argument("--task", default="Click the Continue button if it is safe and visible.")
    parser.add_argument("--config", help="Optional Aoryn YAML config to read model_api_key/model/base URL from.")
    parser.add_argument("--screenshot", help="Optional screenshot path. Defaults to a generated Continue-button image.")
    parser.add_argument("--model", help="Override the computer-use model. Defaults to config model_name or gpt-5.5.")
    parser.add_argument("--api-key", help="Override the API key. Defaults to config model_api_key or OPENAI_API_KEY.")
    parser.add_argument("--base-url", help="Override the API base URL. Defaults to config model_base_url or OpenAI.")
    parser.add_argument("--timeout", type=float, help="Request timeout in seconds. Defaults to config model_request_timeout.")
    args = parser.parse_args()

    config = _build_smoke_config(args)
    api_key = str(config.model_api_key or "").strip()
    if not api_key:
        print("API key is missing; set model_api_key in --config, set OPENAI_API_KEY, or pass --api-key.")
        return 2

    with tempfile.TemporaryDirectory(prefix="aoryn-computer-use-") as temp_dir:
        screenshot_path = Path(args.screenshot) if args.screenshot else Path(temp_dir) / "screen.png"
        if args.screenshot:
            if not screenshot_path.exists():
                print(f"Screenshot does not exist: {screenshot_path}")
                return 2
        else:
            _write_button_screenshot(screenshot_path)
        try:
            result = OpenAIComputerUsePlanner(config).plan(args.task, screenshot_path=screenshot_path, history=[])
        except PlannerError as exc:
            print(f"Computer use smoke failed: {exc}")
            return 1

    payload = {
        "done": result.done,
        "status_summary": result.status_summary,
        "actions": [action.to_dict() for action in result.actions],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _build_smoke_config(args: argparse.Namespace) -> AgentConfig:
    source = AgentConfig.from_yaml(args.config) if args.config else AgentConfig()
    api_key = str(args.api_key or source.model_api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
    model_name = str(args.model or source.model_name or "").strip()
    if not model_name or model_name.lower() == "auto":
        model_name = "gpt-5.5"
    base_url = str(args.base_url or source.model_base_url or "").strip() or "https://api.openai.com/v1"
    return AgentConfig(
        planner_mode="computer_use",
        model_provider=str(source.model_provider or "openai_api").strip() or "openai_api",
        model_base_url=base_url,
        model_name=model_name,
        model_auto_discover=False,
        model_api_key=api_key,
        model_request_timeout=args.timeout if args.timeout is not None else source.model_request_timeout,
        dry_run=True,
    )


def _write_button_screenshot(path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        raise SystemExit("Pillow is required for the computer-use smoke screenshot.") from exc

    image = Image.new("RGB", (640, 360), (246, 247, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle((210, 135, 430, 220), fill=(37, 99, 235), outline=(30, 64, 175), width=2)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except Exception:
        font = ImageFont.load_default()
    draw.text((270, 162), "Continue", fill=(255, 255, 255), font=font)
    image.save(path)


if __name__ == "__main__":
    raise SystemExit(main())
