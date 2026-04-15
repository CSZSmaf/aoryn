from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from desktop_agent.release_bundle import build_release_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Create portable/review release artifacts for Aoryn.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--release-root", required=True)
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--installer-path", required=True)
    args = parser.parse_args()

    payload = build_release_artifacts(
        project_root=Path(args.project_root).resolve(),
        release_root=Path(args.release_root).resolve(),
        release_dir=Path(args.release_dir).resolve(),
        installer_path=Path(args.installer_path).resolve(),
    )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
