import socket
from pathlib import Path

import urllib3.util.connection

from desktop_agent.release_publish import (
    DEFAULT_LATEST_INSTALLER_KEY,
    DEFAULT_INSTALLER_SINGLE_UPLOAD_THRESHOLD,
    DEFAULT_R2_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_R2_READ_TIMEOUT_SECONDS,
    build_botocore_config,
    build_content_disposition,
    build_http_pool_manager,
    build_pages_env_patch,
    build_public_url,
    build_transfer_config,
    installer_object_key,
    proxy_socket_tunnel,
    proxy_scheme,
    proxy_uses_socket_tunnel,
    resolve_proxy_url,
    socks_proxy_support_available,
)


def test_installer_object_key_uses_file_name():
    path = Path("release") / "Aoryn-Setup-0.1.6.exe"
    assert installer_object_key(path) == "Aoryn-Setup-0.1.6.exe"


def test_build_public_url_preserves_nested_key():
    assert (
        build_public_url("https://downloads.aoryn.org/", DEFAULT_LATEST_INSTALLER_KEY)
        == "https://downloads.aoryn.org/latest/Aoryn-Setup-latest.exe"
    )


def test_build_content_disposition_uses_versioned_file_name():
    path = Path("release") / "Aoryn-Setup-0.1.6.exe"
    assert build_content_disposition(path) == 'attachment; filename="Aoryn-Setup-0.1.6.exe"'


def test_build_pages_env_patch_targets_latest_alias():
    payload = build_pages_env_patch(
        "latest/Aoryn-Setup-latest.exe",
        "https://downloads.aoryn.org/latest/Aoryn-Setup-latest.exe",
    )

    production = payload["deployment_configs"]["production"]["env_vars"]
    assert production["AORYN_WINDOWS_INSTALLER_KEY"]["value"] == "latest/Aoryn-Setup-latest.exe"
    assert (
        production["AORYN_WINDOWS_INSTALLER_URL"]["value"]
        == "https://downloads.aoryn.org/latest/Aoryn-Setup-latest.exe"
    )


def test_resolve_proxy_url_prefers_explicit_value(monkeypatch):
    monkeypatch.setenv("AORYN_UPLOAD_PROXY", "https://proxy-from-env:8443")
    monkeypatch.setenv("ALL_PROXY", "http://proxy-from-all:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy-from-https:8081")

    assert resolve_proxy_url("socks5h://127.0.0.1:10808") == "socks5h://127.0.0.1:10808"


def test_resolve_proxy_url_falls_back_to_env_priority(monkeypatch):
    monkeypatch.delenv("AORYN_UPLOAD_PROXY", raising=False)
    monkeypatch.setenv("ALL_PROXY", "http://proxy-from-all:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy-from-https:8081")
    assert resolve_proxy_url(None) == "http://proxy-from-all:8080"

    monkeypatch.setenv("AORYN_UPLOAD_PROXY", "https://proxy-from-aoryn:9443")
    assert resolve_proxy_url(None) == "https://proxy-from-aoryn:9443"


def test_build_botocore_config_includes_proxy_mapping():
    config = build_botocore_config("socks5h://127.0.0.1:10808")
    assert config.proxies == {}
    assert config.connect_timeout == DEFAULT_R2_CONNECT_TIMEOUT_SECONDS
    assert config.read_timeout == DEFAULT_R2_READ_TIMEOUT_SECONDS

    http_proxy_config = build_botocore_config("https://proxy.example:8443")
    assert http_proxy_config.proxies == {
        "http": "https://proxy.example:8443",
        "https": "https://proxy.example:8443",
    }
    assert http_proxy_config.connect_timeout == DEFAULT_R2_CONNECT_TIMEOUT_SECONDS
    assert http_proxy_config.read_timeout == DEFAULT_R2_READ_TIMEOUT_SECONDS


def test_build_transfer_config_prefers_single_request_for_installer_uploads():
    config = build_transfer_config()
    assert config.multipart_threshold == DEFAULT_INSTALLER_SINGLE_UPLOAD_THRESHOLD
    assert config.use_threads is False


def test_build_http_pool_manager_uses_same_http_proxy():
    manager = build_http_pool_manager("https://proxy.example:8443")
    assert manager.__class__.__name__ == "ProxyManager"
    assert str(getattr(manager, "proxy")) == "https://proxy.example:8443"


def test_build_http_pool_manager_keeps_socks_on_direct_pool():
    manager = build_http_pool_manager("socks5h://127.0.0.1:10808")
    assert manager.__class__.__name__ == ("SOCKSProxyManager" if socks_proxy_support_available() else "PoolManager")
    assert proxy_uses_socket_tunnel("socks5h://127.0.0.1:10808")
    assert proxy_scheme("socks5h://127.0.0.1:10808") == "socks5h"


def test_proxy_socket_tunnel_patches_connection_helpers():
    original_socket_create_connection = socket.create_connection
    original_urllib3_create_connection = urllib3.util.connection.create_connection

    with proxy_socket_tunnel("socks5h://127.0.0.1:10808"):
        assert socket.create_connection is not original_socket_create_connection
        assert urllib3.util.connection.create_connection is not original_urllib3_create_connection

    assert socket.create_connection is original_socket_create_connection
    assert urllib3.util.connection.create_connection is original_urllib3_create_connection
