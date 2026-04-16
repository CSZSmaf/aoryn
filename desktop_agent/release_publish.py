from __future__ import annotations

import argparse
from contextlib import contextmanager
import ipaddress
import json
import mimetypes
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

DEFAULT_PUBLIC_BASE_URL = "https://downloads.aoryn.org"
DEFAULT_LATEST_INSTALLER_KEY = "latest/Aoryn-Setup-latest.exe"
DEFAULT_PAGES_PROJECT = "aoryn"
DEFAULT_PROXY_HINT = "socks5h://127.0.0.1:10808"
DEFAULT_R2_CONNECT_TIMEOUT_SECONDS = 300
DEFAULT_R2_READ_TIMEOUT_SECONDS = 300
DEFAULT_INSTALLER_SINGLE_UPLOAD_THRESHOLD = 512 * 1024 * 1024
SUPPORTED_PROXY_SCHEMES = frozenset({"http", "https", "socks5", "socks5h"})
NETWORK_ERROR_CLASS_NAMES = frozenset(
    {
        "ConnectTimeoutError",
        "ConnectionError",
        "EndpointConnectionError",
        "HTTPError",
        "MaxRetryError",
        "NameResolutionError",
        "NewConnectionError",
        "ProtocolError",
        "ProxyConnectionError",
        "ProxyError",
        "ReadTimeoutError",
        "SSLError",
    }
)


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


def normalize_proxy_url(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None

    parsed = urlparse(normalized)
    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_PROXY_SCHEMES:
        supported = ", ".join(sorted(SUPPORTED_PROXY_SCHEMES))
        actual = parsed.scheme or "missing"
        raise RuntimeError(f"Unsupported proxy scheme '{actual}'. Expected one of: {supported}")
    if not parsed.netloc:
        raise RuntimeError(f"Proxy URL must include a host and port: {normalized}")
    return normalized


def resolve_proxy_url(explicit_proxy: str | None) -> str | None:
    candidates = (
        explicit_proxy,
        os.getenv("AORYN_UPLOAD_PROXY"),
        os.getenv("ALL_PROXY"),
        os.getenv("HTTPS_PROXY"),
    )
    for candidate in candidates:
        proxy_url = normalize_proxy_url(candidate)
        if proxy_url:
            return proxy_url
    return None


def proxy_scheme(proxy_url: str | None) -> str | None:
    if not proxy_url:
        return None
    return urlparse(proxy_url).scheme.lower()


def proxy_uses_socket_tunnel(proxy_url: str | None) -> bool:
    return proxy_scheme(proxy_url) in {"socks5", "socks5h"}


def socks_proxy_support_available() -> bool:
    try:
        import socks  # noqa: F401
    except ImportError:
        return False
    return True


def build_proxy_mapping(proxy_url: str | None) -> dict[str, str] | None:
    if not proxy_url:
        return None
    if proxy_uses_socket_tunnel(proxy_url):
        return {}
    return {
        "http": proxy_url,
        "https": proxy_url,
    }


def build_proxy_status(proxy_url: str | None) -> str:
    scheme = proxy_scheme(proxy_url)
    if not scheme:
        return "Installer publish network mode: direct"
    return f"Installer publish network mode: proxy ({scheme})"


def iter_error_chain(error: BaseException):
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        yield current
        seen.add(id(current))
        next_error = current.__cause__ or current.__context__
        current = next_error if isinstance(next_error, BaseException) else None


def looks_like_network_error(error: BaseException) -> bool:
    for candidate in iter_error_chain(error):
        if isinstance(candidate, OSError):
            return True
        if candidate.__class__.__name__ in NETWORK_ERROR_CLASS_NAMES:
            return True
    return False


def build_network_error_message(operation: str, proxy_url: str | None, error: BaseException) -> str:
    detail = str(error) or error.__class__.__name__
    if proxy_url:
        return (
            f"{operation} failed while using proxy ({proxy_scheme(proxy_url)}): {detail}. "
            "Check that the proxy is running and allows outbound HTTPS traffic."
        )
    return (
        f"{operation} failed without a configured proxy: {detail}. "
        f"If your network requires a local proxy, set AORYN_UPLOAD_PROXY={DEFAULT_PROXY_HINT}."
    )


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RuntimeError("SOCKS proxy closed the connection during handshake.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _encode_socks_destination(host: str, port: int, scheme: str) -> bytes:
    if scheme == "socks5h":
        host_bytes = host.encode("idna")
        if len(host_bytes) > 255:
            raise RuntimeError(f"Target host is too long for SOCKS5: {host}")
        return b"\x03" + bytes([len(host_bytes)]) + host_bytes + port.to_bytes(2, "big")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        address = ipaddress.ip_address(resolved[0][4][0])

    atyp = b"\x01" if address.version == 4 else b"\x04"
    return atyp + address.packed + port.to_bytes(2, "big")


def _consume_socks_reply(sock: socket.socket, atyp: int) -> None:
    if atyp == 1:
        _recv_exact(sock, 4)
    elif atyp == 3:
        domain_length = _recv_exact(sock, 1)[0]
        _recv_exact(sock, domain_length)
    elif atyp == 4:
        _recv_exact(sock, 16)
    else:
        raise RuntimeError(f"SOCKS proxy returned an unknown address type: {atyp}")
    _recv_exact(sock, 2)


def _negotiate_socks_connection(
    sock: socket.socket,
    proxy_url: str,
    target_host: str,
    target_port: int,
) -> None:
    parsed = urlparse(proxy_url)
    username = parsed.username or ""
    password = parsed.password or ""

    methods = [0x00]
    if username or password:
        methods.insert(0, 0x02)
    sock.sendall(bytes([0x05, len(methods), *methods]))

    greeting = _recv_exact(sock, 2)
    if greeting[0] != 0x05:
        raise RuntimeError("SOCKS proxy returned an invalid greeting version.")
    if greeting[1] == 0xFF:
        raise RuntimeError("SOCKS proxy rejected all supported authentication methods.")
    if greeting[1] == 0x02:
        if not (username or password):
            raise RuntimeError("SOCKS proxy requires username/password authentication.")
        username_bytes = username.encode("utf-8")
        password_bytes = password.encode("utf-8")
        if len(username_bytes) > 255 or len(password_bytes) > 255:
            raise RuntimeError("SOCKS proxy credentials are too long.")
        sock.sendall(
            bytes([0x01, len(username_bytes)])
            + username_bytes
            + bytes([len(password_bytes)])
            + password_bytes
        )
        auth_reply = _recv_exact(sock, 2)
        if auth_reply[1] != 0x00:
            raise RuntimeError("SOCKS proxy username/password authentication failed.")
    elif greeting[1] != 0x00:
        raise RuntimeError(f"SOCKS proxy selected unsupported auth method: {greeting[1]}")

    destination = _encode_socks_destination(target_host, target_port, proxy_scheme(proxy_url) or "socks5")
    sock.sendall(b"\x05\x01\x00" + destination)

    reply = _recv_exact(sock, 4)
    if reply[0] != 0x05:
        raise RuntimeError("SOCKS proxy returned an invalid response version.")
    if reply[1] != 0x00:
        error_names = {
            0x01: "general failure",
            0x02: "connection not allowed",
            0x03: "network unreachable",
            0x04: "host unreachable",
            0x05: "connection refused",
            0x06: "TTL expired",
            0x07: "command not supported",
            0x08: "address type not supported",
        }
        raise RuntimeError(f"SOCKS proxy connect failed: {error_names.get(reply[1], f'error {reply[1]}')}")
    _consume_socks_reply(sock, reply[3])


@contextmanager
def proxy_socket_tunnel(proxy_url: str | None):
    if not proxy_uses_socket_tunnel(proxy_url):
        yield
        return

    import urllib3.util.connection as urllib3_connection

    parsed = urlparse(proxy_url or "")
    proxy_host = parsed.hostname
    proxy_port = parsed.port
    if not proxy_host or not proxy_port:
        raise RuntimeError(f"Proxy URL must include a host and port: {proxy_url}")

    original_socket_create_connection = socket.create_connection
    original_urllib3_create_connection = urllib3_connection.create_connection

    def create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, socket_options=None):
        sock = None
        try:
            sock = original_socket_create_connection((proxy_host, proxy_port), timeout, source_address)
            if socket_options:
                for option in socket_options:
                    sock.setsockopt(*option)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            target_host, target_port = address
            _negotiate_socks_connection(sock, proxy_url or "", str(target_host), int(target_port))
            return sock
        except Exception:
            if sock is not None:
                sock.close()
            raise

    socket.create_connection = create_connection
    urllib3_connection.create_connection = create_connection
    try:
        yield
    finally:
        socket.create_connection = original_socket_create_connection
        urllib3_connection.create_connection = original_urllib3_create_connection


def build_http_pool_manager(proxy_url: str | None):
    import urllib3

    timeout = urllib3.Timeout(connect=30.0, read=30.0)
    if not proxy_url:
        return urllib3.PoolManager(timeout=timeout, retries=False)
    if proxy_uses_socket_tunnel(proxy_url):
        if socks_proxy_support_available():
            from urllib3.contrib.socks import SOCKSProxyManager

            return SOCKSProxyManager(proxy_url, timeout=timeout, retries=False)
        return urllib3.PoolManager(timeout=timeout, retries=False)
    return urllib3.ProxyManager(proxy_url, timeout=timeout, retries=False)


def cloudflare_api_request(
    api_token: str,
    account_id: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    proxy_url: str | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    manager = build_http_pool_manager(proxy_url)
    response = None
    try:
        response = manager.request(
            method,
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}{path}",
            body=body,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
        )
        payload_text = response.data.decode("utf-8", errors="replace")
        if response.status >= 400:
            raise RuntimeError(f"Cloudflare API {method} {path} failed: {payload_text}")
        return json.loads(payload_text)
    except RuntimeError:
        raise
    except Exception as error:
        if looks_like_network_error(error):
            raise RuntimeError(build_network_error_message(f"Cloudflare API {method} {path}", proxy_url, error)) from error
        raise
    finally:
        if response is not None:
            response.release_conn()


def update_pages_download_settings(
    *,
    api_token: str,
    account_id: str,
    project_name: str,
    latest_key: str,
    latest_url: str,
    proxy_url: str | None = None,
) -> dict[str, Any]:
    return cloudflare_api_request(
        api_token,
        account_id,
        "PATCH",
        f"/pages/projects/{project_name}",
        build_pages_env_patch(latest_key, latest_url),
        proxy_url=proxy_url,
    )


def retry_latest_pages_deployment(
    *,
    api_token: str,
    account_id: str,
    project_name: str,
    proxy_url: str | None = None,
) -> str:
    deployments = cloudflare_api_request(
        api_token,
        account_id,
        "GET",
        f"/pages/projects/{project_name}/deployments",
        proxy_url=proxy_url,
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
        proxy_url=proxy_url,
    )
    result = response.get("result") or {}
    return str(result.get("id") or production["id"])


def require_value(name: str, value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise RuntimeError(f"Missing required setting: {name}")
    return normalized


def build_botocore_config(proxy_url: str | None):
    try:
        from botocore.config import Config
    except ImportError as error:
        raise RuntimeError(
            "boto3 is required for installer publishing. Run `python -m pip install --user -r requirements-build.txt` first."
        ) from error

    config_kwargs: dict[str, Any] = {
        "signature_version": "s3v4",
        "connect_timeout": DEFAULT_R2_CONNECT_TIMEOUT_SECONDS,
        "read_timeout": DEFAULT_R2_READ_TIMEOUT_SECONDS,
    }
    proxy_mapping = build_proxy_mapping(proxy_url)
    if proxy_mapping is not None:
        config_kwargs["proxies"] = proxy_mapping
    return Config(**config_kwargs)


def build_transfer_config():
    try:
        from boto3.s3.transfer import TransferConfig
    except ImportError as error:
        raise RuntimeError(
            "boto3 is required for installer publishing. Run `python -m pip install --user -r requirements-build.txt` first."
        ) from error

    return TransferConfig(
        multipart_threshold=DEFAULT_INSTALLER_SINGLE_UPLOAD_THRESHOLD,
        use_threads=False,
    )


def build_r2_client(account_id: str, access_key_id: str, secret_access_key: str, proxy_url: str | None = None):
    try:
        import boto3
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
        config=build_botocore_config(proxy_url),
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
        Config=build_transfer_config(),
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
    parser.add_argument("--proxy")
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
    proxy_url = resolve_proxy_url(args.proxy)

    print(build_proxy_status(proxy_url))

    pages_synced = False
    pages_redeploy_id = None
    with proxy_socket_tunnel(proxy_url):
        try:
            client = build_r2_client(account_id, access_key_id, secret_access_key, proxy_url=proxy_url)
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
        except RuntimeError:
            raise
        except Exception as error:
            if looks_like_network_error(error):
                raise RuntimeError(build_network_error_message("Cloudflare R2 upload", proxy_url, error)) from error
            raise

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
                proxy_url=proxy_url,
            )
            pages_synced = True
        if args.retry_pages_deployment:
            pages_redeploy_id = retry_latest_pages_deployment(
                api_token=api_token,
                account_id=account_id,
                project_name=project_name,
                proxy_url=proxy_url,
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
