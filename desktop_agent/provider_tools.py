from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class ProviderToolError(RuntimeError):
    """Raised when provider inspection or model management fails."""


@dataclass(slots=True)
class ProviderModelEntry:
    model_id: str
    label: str
    kind: str | None = None
    loaded: bool = False
    loaded_instance_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.model_id,
            "label": self.label,
            "kind": self.kind,
            "loaded": self.loaded,
            "loaded_instance_ids": list(self.loaded_instance_ids),
        }


@dataclass(slots=True)
class ProviderSnapshot:
    ok: bool
    provider: str
    api_base: str
    root_base: str
    loaded_models: list[str]
    catalog_models: list[ProviderModelEntry]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "api_base": self.api_base,
            "root_base": self.root_base,
            "loaded_models": list(self.loaded_models),
            "catalog_models": [item.to_dict() for item in self.catalog_models],
            "error": self.error,
        }


def fetch_provider_snapshot(
    *,
    provider: str,
    base_url: str,
    api_key: str | None,
    timeout: float,
    requests_module=None,
) -> ProviderSnapshot:
    requests = requests_module or _import_requests()
    api_base = normalize_api_base_url(base_url)
    root_base = provider_root_base(api_base)
    headers = build_request_headers(api_key)

    loaded_models: list[str] = []
    catalog_models: list[ProviderModelEntry] = []
    openai_model_ids: list[str] = []
    errors: list[str] = []

    try:
        response = requests.get(
            f"{api_base}/models",
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        openai_model_ids = _extract_loaded_model_ids(response.json())
        if provider != "lmstudio_local":
            loaded_models = list(openai_model_ids)
            catalog_models.extend(
                ProviderModelEntry(model_id=model_id, label=model_id, loaded=True)
                for model_id in loaded_models
            )
    except Exception as exc:
        errors.append(_format_provider_models_error(provider=provider, path="/v1/models", exc=exc))

    if provider == "lmstudio_local":
        try:
            response = requests.get(
                f"{root_base}/api/v1/models",
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            catalog_models = _merge_model_catalog(
                catalog_models,
                _extract_lmstudio_catalog(response.json()),
            )
            loaded_models = [item.model_id for item in catalog_models if item.loaded]
            catalog_models = _merge_model_catalog(
                catalog_models,
                [ProviderModelEntry(model_id=model_id, label=model_id, loaded=False) for model_id in openai_model_ids],
            )
        except Exception as exc:
            errors.append(_format_provider_models_error(provider=provider, path="/api/v1/models", exc=exc))
            if openai_model_ids:
                loaded_models = list(openai_model_ids)
                catalog_models = _merge_model_catalog(
                    catalog_models,
                    [ProviderModelEntry(model_id=model_id, label=model_id, loaded=True) for model_id in openai_model_ids],
                )

    ok = bool(loaded_models or catalog_models)
    error = None if ok else " | ".join(errors) or "No models were returned by the provider."
    return ProviderSnapshot(
        ok=ok,
        provider=provider,
        api_base=api_base,
        root_base=root_base,
        loaded_models=loaded_models,
        catalog_models=catalog_models,
        error=error,
    )


def load_lmstudio_model(
    *,
    base_url: str,
    api_key: str | None,
    model_id: str,
    timeout: float,
    requests_module=None,
) -> dict[str, Any]:
    requests = requests_module or _import_requests()
    if not model_id.strip():
        raise ProviderToolError("A model id is required.")

    api_base = normalize_api_base_url(base_url)
    root_base = provider_root_base(api_base)
    headers = build_request_headers(api_key)
    url = f"{root_base}/api/v1/models/load"

    payloads = (
        {"model": model_id},
        {"key": model_id},
        {"id": model_id},
        {"model_id": model_id},
    )
    last_response_text = ""

    for payload in payloads:
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except Exception as exc:
            raise ProviderToolError(f"Could not reach LM Studio model load endpoint: {exc}") from exc

        if response.status_code < 400:
            return {
                "ok": True,
                "api_base": api_base,
                "root_base": root_base,
                "model_id": model_id,
                "request_payload": payload,
                "response": _safe_json_or_text(response),
            }

        last_response_text = (getattr(response, "text", "") or "").strip()
        lowered = last_response_text.lower()
        if any(token in lowered for token in ("required", "missing", "invalid", "unknown field")):
            continue

    raise ProviderToolError(
        "LM Studio rejected the model load request. "
        f"Last response: {last_response_text or '<empty>'}"
    )


def unload_lmstudio_model_instances(
    *,
    base_url: str,
    api_key: str | None,
    instance_ids: list[str],
    timeout: float,
    requests_module=None,
) -> dict[str, Any]:
    requests = requests_module or _import_requests()
    api_base = normalize_api_base_url(base_url)
    root_base = provider_root_base(api_base)
    headers = build_request_headers(api_key)
    url = f"{root_base}/api/v1/models/unload"

    normalized_ids: list[str] = []
    for instance_id in instance_ids:
        candidate = str(instance_id or "").strip()
        if candidate and candidate not in normalized_ids:
            normalized_ids.append(candidate)

    unloaded_ids: list[str] = []
    for instance_id in normalized_ids:
        try:
            response = requests.post(
                url,
                headers=headers,
                json={"instance_id": instance_id},
                timeout=timeout,
            )
        except Exception as exc:
            raise ProviderToolError(f"Could not reach LM Studio model unload endpoint: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderToolError(
                "LM Studio rejected the model unload request. "
                f"Instance: {instance_id}. Last response: {(getattr(response, 'text', '') or '').strip() or '<empty>'}"
            )

        payload = _safe_json_or_text(response)
        if isinstance(payload, dict):
            unloaded_ids.append(str(payload.get("instance_id") or instance_id).strip() or instance_id)
        else:
            unloaded_ids.append(instance_id)

    return {
        "ok": True,
        "api_base": api_base,
        "root_base": root_base,
        "unloaded_instance_ids": unloaded_ids,
    }


def normalize_api_base_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        raw = "http://127.0.0.1:1234/v1"
    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlsplit(raw)
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]
    elif path.endswith("/models"):
        path = path[: -len("/models")]
    if not path:
        path = "/v1"
    elif path != "/v1" and not path.endswith("/v1"):
        path = f"{path}/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def provider_root_base(api_base: str) -> str:
    parsed = urlsplit(api_base)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")


def build_request_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    normalized_api_key = str(api_key or "").strip()
    if normalized_api_key:
        headers["Authorization"] = f"Bearer {normalized_api_key}"
    return headers


def _format_provider_models_error(*, provider: str, path: str, exc: Exception) -> str:
    message = str(exc)
    prefix = f"Could not read {path}: "
    if provider == "openai_api" and ("401" in message or "unauthorized" in message.lower()):
        return (
            f"{prefix}OpenAI returned 401 Unauthorized. "
            "Check that the API key is active, pasted without extra spaces or newlines, "
            "and comes from platform.openai.com."
        )
    return f"{prefix}{message}"


def _extract_loaded_model_ids(payload: Any) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []

    models: list[str] = []
    for item in data:
        if isinstance(item, dict):
            model_id = str(item.get("id", "")).strip()
        else:
            model_id = str(item).strip()
        if model_id and model_id not in models:
            models.append(model_id)
    return models


def _extract_lmstudio_catalog(payload: Any) -> list[ProviderModelEntry]:
    items = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []

    catalog: list[ProviderModelEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("key") or item.get("id") or "").strip()
        if not model_id:
            continue
        label = str(item.get("display_name") or model_id).strip()
        kind = str(item.get("type") or "").strip() or None
        raw_loaded_instances = item.get("loaded_instances")
        loaded_instance_ids: list[str] = []
        if isinstance(raw_loaded_instances, list):
            for loaded_instance in raw_loaded_instances:
                if not isinstance(loaded_instance, dict):
                    continue
                instance_id = str(loaded_instance.get("id") or "").strip()
                if instance_id and instance_id not in loaded_instance_ids:
                    loaded_instance_ids.append(instance_id)
        loaded = bool(loaded_instance_ids)
        catalog.append(
            ProviderModelEntry(
                model_id=model_id,
                label=label,
                kind=kind,
                loaded=loaded,
                loaded_instance_ids=loaded_instance_ids,
            )
        )
    return catalog


def _merge_model_catalog(
    base_entries: list[ProviderModelEntry],
    extra_entries: list[ProviderModelEntry],
) -> list[ProviderModelEntry]:
    merged: dict[str, ProviderModelEntry] = {item.model_id: item for item in base_entries}
    for item in extra_entries:
        existing = merged.get(item.model_id)
        if existing is None:
            merged[item.model_id] = item
            continue
        merged[item.model_id] = ProviderModelEntry(
            model_id=item.model_id,
            label=item.label or existing.label,
            kind=item.kind or existing.kind,
            loaded=existing.loaded or item.loaded,
            loaded_instance_ids=[
                *existing.loaded_instance_ids,
                *[instance_id for instance_id in item.loaded_instance_ids if instance_id not in existing.loaded_instance_ids],
            ],
        )
    return list(merged.values())


def _safe_json_or_text(response) -> Any:
    try:
        return response.json()
    except Exception:
        return (getattr(response, "text", "") or "").strip()


def _import_requests():
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise ProviderToolError(
            "The requests package is required to inspect model providers."
        ) from exc
    return requests
