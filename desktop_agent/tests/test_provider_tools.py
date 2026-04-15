from desktop_agent.provider_tools import (
    ProviderToolError,
    build_request_headers,
    fetch_provider_snapshot,
    load_lmstudio_model,
    normalize_api_base_url,
    provider_root_base,
    unload_lmstudio_model_instances,
)


class _FakeResponse:
    def __init__(self, *, payload=None, status_code=200, text="") -> None:
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.text or f"HTTP {self.status_code}")


class _FakeRequests:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return self.responses[("GET", url)]

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs.get("json")))
        return self.responses[("POST", url, str(kwargs.get("json")))]


def test_provider_url_helpers():
    api_base = normalize_api_base_url("127.0.0.1:1234")

    assert api_base == "http://127.0.0.1:1234/v1"
    assert provider_root_base(api_base) == "http://127.0.0.1:1234"


def test_build_request_headers_trims_api_key_whitespace():
    headers = build_request_headers("  sk-test-key \n")

    assert headers["Authorization"] == "Bearer sk-test-key"


def test_fetch_provider_snapshot_reads_lmstudio_catalog():
    requests = _FakeRequests(
        {
            ("GET", "http://127.0.0.1:1234/v1/models"): _FakeResponse(
                payload={"data": [{"id": "qwen/qwen3-vl-30b"}, {"id": "qwen/qwen3.5-9b"}]}
            ),
            ("GET", "http://127.0.0.1:1234/api/v1/models"): _FakeResponse(
                payload={
                    "models": [
                        {
                            "key": "qwen/qwen3-vl-30b",
                            "display_name": "Qwen3 VL 30B",
                            "type": "llm",
                            "loaded_instances": [{"id": "qwen/qwen3-vl-30b"}],
                        },
                        {
                            "key": "qwen/qwen3.5-9b",
                            "display_name": "Qwen3.5 9B",
                            "type": "llm",
                            "loaded_instances": [],
                        },
                    ]
                }
            ),
        }
    )

    snapshot = fetch_provider_snapshot(
        provider="lmstudio_local",
        base_url="http://127.0.0.1:1234/v1",
        api_key=None,
        timeout=5,
        requests_module=requests,
    )

    assert snapshot.ok is True
    assert snapshot.loaded_models == ["qwen/qwen3-vl-30b"]
    assert any(item.model_id == "qwen/qwen3.5-9b" and item.loaded is False for item in snapshot.catalog_models)
    assert any(item.model_id == "qwen/qwen3-vl-30b" and item.loaded is True for item in snapshot.catalog_models)
    assert any(
        item.model_id == "qwen/qwen3-vl-30b" and item.loaded_instance_ids == ["qwen/qwen3-vl-30b"]
        for item in snapshot.catalog_models
    )


def test_fetch_provider_snapshot_reports_openai_unauthorized_helpfully():
    requests = _FakeRequests(
        {
            ("GET", "https://api.openai.com/v1/models"): _FakeResponse(
                status_code=401,
                text="401 Client Error: Unauthorized for url: https://api.openai.com/v1/models",
            ),
        }
    )

    snapshot = fetch_provider_snapshot(
        provider="openai_api",
        base_url="https://api.openai.com/v1",
        api_key="  sk-test \n",
        timeout=5,
        requests_module=requests,
    )

    assert snapshot.ok is False
    assert "OpenAI returned 401 Unauthorized" in snapshot.error
    assert "without extra spaces or newlines" in snapshot.error


def test_load_lmstudio_model_accepts_first_successful_payload():
    url = "http://127.0.0.1:1234/api/v1/models/load"
    requests = _FakeRequests(
        {
            ("POST", url, "{'model': 'qwen/qwen3.5-9b'}"): _FakeResponse(
                payload={"ok": True, "status": "loading"}
            ),
        }
    )

    result = load_lmstudio_model(
        base_url="http://127.0.0.1:1234/v1",
        api_key=None,
        model_id="qwen/qwen3.5-9b",
        timeout=5,
        requests_module=requests,
    )

    assert result["ok"] is True
    assert result["model_id"] == "qwen/qwen3.5-9b"


def test_load_lmstudio_model_raises_when_every_payload_fails():
    url = "http://127.0.0.1:1234/api/v1/models/load"
    requests = _FakeRequests(
        {
            ("POST", url, "{'model': 'missing-model'}"): _FakeResponse(status_code=400, text="missing field"),
            ("POST", url, "{'key': 'missing-model'}"): _FakeResponse(status_code=400, text="missing field"),
            ("POST", url, "{'id': 'missing-model'}"): _FakeResponse(status_code=400, text="invalid model"),
            ("POST", url, "{'model_id': 'missing-model'}"): _FakeResponse(status_code=400, text="invalid model"),
        }
    )

    try:
        load_lmstudio_model(
            base_url="http://127.0.0.1:1234/v1",
            api_key=None,
            model_id="missing-model",
            timeout=5,
            requests_module=requests,
        )
    except ProviderToolError as exc:
        assert "LM Studio rejected" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ProviderToolError to be raised.")


def test_unload_lmstudio_model_instances_posts_instance_ids():
    url = "http://127.0.0.1:1234/api/v1/models/unload"
    requests = _FakeRequests(
        {
            ("POST", url, "{'instance_id': 'qwen/qwen3-vl-30b'}"): _FakeResponse(
                payload={"ok": True, "instance_id": "qwen/qwen3-vl-30b"}
            ),
        }
    )

    result = unload_lmstudio_model_instances(
        base_url="http://127.0.0.1:1234/v1",
        api_key=None,
        instance_ids=["qwen/qwen3-vl-30b"],
        timeout=5,
        requests_module=requests,
    )

    assert result["ok"] is True
    assert result["unloaded_instance_ids"] == ["qwen/qwen3-vl-30b"]
