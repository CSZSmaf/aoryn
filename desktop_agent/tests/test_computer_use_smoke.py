from argparse import Namespace

from scripts.smoke_computer_use_api import _build_smoke_config


def test_smoke_config_reads_yaml_api_key_without_using_local_model(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "model_provider: lmstudio_local",
                "model_base_url: http://127.0.0.1:1234/v1",
                "model_name: auto",
                "model_api_key: config-secret",
                "model_request_timeout: 17",
            ]
        ),
        encoding="utf-8",
    )

    config = _build_smoke_config(
        Namespace(
            config=str(config_path),
            api_key=None,
            model=None,
            base_url=None,
            timeout=12.0,
        )
    )

    assert config.planner_mode == "computer_use"
    assert config.model_name == "gpt-5.5"
    assert config.model_api_key == "config-secret"
    assert config.model_request_timeout == 12.0


def test_smoke_config_cli_args_override_config_and_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model_api_key: config-secret\nmodel_name: config-model\n", encoding="utf-8")

    config = _build_smoke_config(
        Namespace(
            config=str(config_path),
            api_key="cli-secret",
            model="gpt-5.5",
            base_url="https://api.openai.com/v1",
            timeout=None,
        )
    )

    assert config.model_api_key == "cli-secret"
    assert config.model_name == "gpt-5.5"
    assert config.model_base_url == "https://api.openai.com/v1"
