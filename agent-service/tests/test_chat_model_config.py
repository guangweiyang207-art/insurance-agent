"""Model construction needs settings values, not a populated process environment."""

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from langchain_deepseek import ChatDeepSeek


@pytest.fixture
def chat_model_config(monkeypatch):
    app_root = Path(__file__).resolve().parents[1]
    fake_settings = SimpleNamespace(
        deepseek_api_key="sk-unit-test-only",
        deepseek_base_url="https://api.deepseek.com",
        chat_model="deepseek-flash",
    )
    # Replace only this import while loading the real implementation. Importing
    # the production Settings singleton here would read the developer's .env.
    config = ModuleType("app.core.config")
    config.APP_ROOT = app_root
    config.settings = fake_settings
    spec = importlib.util.spec_from_file_location(
        "app.core.chat_model", app_root / "app" / "core" / "chat_model.py"
    )
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as isolated_import:
        isolated_import.setitem(sys.modules, "app.core.config", config)
        spec.loader.exec_module(module)

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_BASE", raising=False)
    return module, fake_settings, app_root


def test_settings_key_constructs_real_model_without_environment(chat_model_config):
    module, settings, _ = chat_model_config

    model = module.create_chat_model()

    assert "DEEPSEEK_API_KEY" not in os.environ
    assert isinstance(model, ChatDeepSeek)
    assert model.api_key.get_secret_value() == settings.deepseek_api_key
    assert model.api_base == settings.deepseek_base_url
    assert str(model.root_client.base_url).rstrip("/") == settings.deepseek_base_url
    assert model.model_name == settings.chat_model


def test_model_override_base_url_and_extra_body_are_preserved(chat_model_config):
    module, settings, _ = chat_model_config
    settings.deepseek_base_url = "https://deepseek-unit-test.invalid/v1"
    extra_body = {"thinking": {"type": "disabled"}}

    model = module.create_chat_model(model="custom-chat-model", extra_body=extra_body)

    assert isinstance(model, ChatDeepSeek)
    assert model.model_name == "custom-chat-model"
    assert model.api_base == settings.deepseek_base_url
    assert str(model.root_client.base_url).rstrip("/") == settings.deepseek_base_url
    assert model.extra_body == extra_body
    assert model.api_key.get_secret_value() == settings.deepseek_api_key


@pytest.mark.parametrize("missing_key", [None, "", "   "])
def test_missing_key_points_to_local_env_file(chat_model_config, missing_key):
    module, settings, app_root = chat_model_config
    settings.deepseek_api_key = missing_key

    with pytest.raises(RuntimeError) as error:
        module.create_chat_model()

    assert "DEEPSEEK_API_KEY" in str(error.value)
    assert str(app_root / ".env") in str(error.value)
