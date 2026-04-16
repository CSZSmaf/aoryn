from __future__ import annotations

import argparse
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_PUBLIC_BASE_URL = "https://downloads.aoryn.org"
DEFAULT_LATEST_INSTALLER_KEY = "latest/Aoryn-Setup-latest.exe"
DEFAULT_PAGES_PROJECT = "aoryn"


@dataclass(frozen=True)
class PublishSummary:
    installer_path: str
    versioned_key: str
    latest_key: str
    versioned_url: str
    latest_url: str
    pages_synced: bool
    pages_redeploy_id: str | None


def installer_object_key(installer_path: Path) -> str:
    return installer_path.name


def build_public_url(base_url: str, object_key: str) -> str:
    normalized_base = str(base_url or DEFAULT_PUBLIC_BASE_URL).strip().rstrip("/")
    normalized_key = quote(str(object_key).lstrip("/"), safe="/")
    return f"{normalized_base}/{normalized_key}"


def guess_content_type(file_name: str) -> str:
    guessed = mimetypes.guess_type(file_name)[0]
    if guessed:
        return guessed
    if file_name.lower().endswith(".exe"):
        return "application/vnd.microsoft.portable-executable"
    return "application/octet-stream"


def build_download_name(installer_path: Path) -> str:
    return installer_path.name


def build_content_disposition(installer_path: Path) -> str:
    return f'attachment; filename="{build_download_name(installer_path)}"'


def build_pages_env_patch(latest_key: str, latest_url: str) -> dict[str, Any]:
    return {
        "deployment_configs": {
            "production": {
                "env_vars": {
                    "AORYN_WINDOWS_INSTALLER_KEY": {
                        "type": "plain_text",
                        "value": latest_key,
                    },
                    "AORYN_WINDOWS_INSTALLER_URL": {
                        "type": "plain_text",
                        "value": latest_url,
                    },
                }
            }
        }
    }


def cloudflare_api_request(
    api_token: str,
    account_id: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url=f"https://api.cloudflare.com/client/v4/accounts/{account_id}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cloudflare API {method} {path} failed: {details}") from error
    except URLError as error:
        raise RuntimeError(f"Cloudflare API {method} {path} failed: {error}") from error


def update_pages_download_settings(
    *,
    api_token: str,
    account_id: str,
    project_name: str,
    latest_key: str,
    latest_url: str,
) -> dict[str, Any]:
    return cloudflare_api_request(
        api_token,
        account_id,
        "PATCH",
        f"/pages/projects/{project_name}",
        build_pages_env_patch(latest_key, latest_url),
    )


def retry_latest_pages_deployment(
    *,
    api_token: str,
    account_id: str,
    project_name: str,
) -> str:
    deployments = cloudflare_api_request(
        api_token,
        account_id,
        "GET",
        f"/pages/projects/{project_name}/deployments",
    )
    production = next(
        (item for item in deployments.get("result", []) if item.get("environment") == "production"),
        None,
    )
    if not production or not production.get("id"):
        raise RuntimeError("Could not find a production Pages deployment to retry.")

    response = cloudflare_api_request(
        api_token,
        account_id,
        "POST",
        f"/pages/projects/{project_name}/deployments/{production['id']}/retry",
        {},
    )
    result = response.get("result") or {}
    return str(result.get("id") or production["id"])


def require_value(name: str, value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise RuntimeError(f"Missing required setting: {name}")
    return normalized


def build_r2_client(account_id: str, access_key_id: str, secret_access_key: str):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as error:
        raise RuntimeError(
            "boto3 is required for installer publishing. Run `python -m pip install --user -r requirements-build.txt` first."
        ) from error

    endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def upload_installer_object(
    *,
    client: Any,
    bucket: str,
    installer_path: Path,
    object_key: str,
    cache_control: str,
) -> None:
    client.upload_file(
        str(installer_path),
        bucket,
        object_key,
        ExtraArgs={
            "ContentType": guess_content_type(installer_path.name),
            "ContentDisposition": build_content_disposition(installer_path),
            "CacheControl": cache_control,
        },
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload the Windows installer to Cloudflare R2.")
    parser.add_argument("--installer-path", required=True)
    parser.add_argument("--account-id", default=os.getenv("AORYN_R2_ACCOUNT_ID"))
    parser.add_argument("--bucket", default=os.getenv("AORYN_R2_BUCKET", "aoryn-downloads"))
    parser.add_argument("--access-key-id", default=os.getenv("AORYN_R2_ACCESS_KEY_ID"))
    parser.add_argument("--secret-access-key", default=os.getenv("AORYN_R2_SECRET_ACCESS_KEY"))
    parser.add_argument("--public-base-url", default=os.getenv("AORYN_R2_PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL))
    parser.add_argument("--latest-key", default=os.getenv("AORYN_R2_LATEST_KEY", DEFAULT_LATEST_INSTALLER_KEY))
    parser.add_argument("--cf-api-token", default=os.getenv("AORYN_CF_API_TOKEN"))
    parser.add_argument("--pages-project", default=os.getenv("AORYN_PAGES_PROJECT", DEFAULT_PAGES_PROJECT))
    parser.add_argument("--sync-pages-download-settings", action="store_true")
    parser.add_argument("--retry-pages-deployment", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    installer_path = Path(args.installer_path).resolve()
    if not installer_path.is_file():
        raise RuntimeError(f"Installer not found: {installer_path}")

    account_id = require_value("AORYN_R2_ACCOUNT_ID", args.account_id)
    bucket = require_value("AORYN_R2_BUCKET", args.bucket)
    access_key_id = require_value("AORYN_R2_ACCESS_KEY_ID", args.access_key_id)
    secret_access_key = require_value("AORYN_R2_SECRET_ACCESS_KEY", args.secret_access_key)

    versioned_key = installer_object_key(installer_path)
    latest_key = require_value("AORYN_R2_LATEST_KEY", args.latest_key)
    public_base_url = require_value("AORYN_R2_PUBLIC_BASE_URL", args.public_base_url)
    versioned_url = build_public_url(public_base_url, versioned_key)
    latest_url = build_public_url(public_base_url, latest_key)

    client = build_r2_client(account_id, access_key_id, secret_access_key)
    upload_installer_object(
        client=client,
        bucket=bucket,
        installer_path=installer_path,
        object_key=versioned_key,
        cache_control="public, max-age=31536000, immutable",
    )
    upload_installer_object(
        client=client,
        bucket=bucket,
        installer_path=installer_path,
        object_key=latest_key,
        cache_control="no-store",
    )

    pages_synced = False
    pages_redeploy_id = None
    if args.sync_pages_download_settings or args.retry_pages_deployment:
        api_token = require_value("AORYN_CF_API_TOKEN", args.cf_api_token)
        project_name = require_value("AORYN_PAGES_PROJECT", args.pages_project)
        if args.sync_pages_download_settings:
            update_pages_download_settings(
                api_token=api_token,
                account_id=account_id,
                project_name=project_name,
                latest_key=latest_key,
                latest_url=latest_url,
            )
            pages_synced = True
        if args.retry_pages_deployment:
            pages_redeploy_id = retry_latest_pages_deployment(
                api_token=api_token,
                account_id=account_id,
                project_name=project_name,
            )

    summary = PublishSummary(
        installer_path=str(installer_path),
        versioned_key=versioned_key,
        latest_key=latest_key,
        versioned_url=versioned_url,
        latest_url=latest_url,
        pages_synced=pages_synced,
        pages_redeploy_id=pages_redeploy_id,
    )
    print(json.dumps(summary.__dict__, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
