import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Any
import litellm

from src.domain.enums import LLMProvider
from src.infrastructure.config import settings
from src.infrastructure.llm.litellm_adapter import LiteLLMAdapter
from src.infrastructure.llm.provider_resolver import LLMProviderResolver
from src.ports.llm_gateway import LLMRequest, LLMMessage


def _build_mock_response(content: str = "Test response", prompt_tokens: int = 50, completion_tokens: int = 25):
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = None
    choice.finish_reason = "stop"

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


def test_llm_provider_enum_supports_modern_providers():
    assert LLMProvider.ANTHROPIC.value == "anthropic"
    assert LLMProvider.OPENAI.value == "openai"
    assert LLMProvider.DEEPSEEK.value == "deepseek"
    assert LLMProvider.CUSTOM.value == "custom"


def test_provider_resolver_maps_anthropic_and_openai_to_litellm():
    resolver = LLMProviderResolver()
    adapter_anthropic = resolver._get_adapter(LLMProvider.ANTHROPIC)
    assert isinstance(adapter_anthropic, LiteLLMAdapter)

    adapter_openai = resolver._get_adapter(LLMProvider.OPENAI)
    assert isinstance(adapter_openai, LiteLLMAdapter)

    adapter_custom = resolver._get_adapter(LLMProvider.CUSTOM)
    assert isinstance(adapter_custom, LiteLLMAdapter)


def test_litellm_adapter_model_identifier_formatting():
    adapter = LiteLLMAdapter()
    # Anthropic
    assert adapter._format_model_identifier(LLMProvider.ANTHROPIC, "claude-3-5-sonnet-20241022") == "anthropic/claude-3-5-sonnet-20241022"
    assert adapter._format_model_identifier(LLMProvider.ANTHROPIC, "anthropic/claude-3-opus") == "anthropic/claude-3-opus"

    # OpenAI
    assert adapter._format_model_identifier(LLMProvider.OPENAI, "gpt-4o") == "openai/gpt-4o"
    assert adapter._format_model_identifier(LLMProvider.OPENAI, "openai/gpt-4o-mini") == "openai/gpt-4o-mini"

    # Custom
    assert adapter._format_model_identifier(LLMProvider.CUSTOM, "deepseek-coder") == "openai/deepseek-coder"


def test_litellm_adapter_api_key_resolution(monkeypatch):
    adapter = LiteLLMAdapter()
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test-key-123")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-openai-test-456")

    assert adapter._get_api_key(LLMProvider.ANTHROPIC) == "sk-ant-test-key-123"
    assert adapter._get_api_key(LLMProvider.OPENAI) == "sk-openai-test-456"


@pytest.mark.asyncio
async def test_litellm_adapter_completes_anthropic_claude_request(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-real-looking-key")

    mock_resp = _build_mock_response(content="Claude Architecture Analysis Completed.", prompt_tokens=450, completion_tokens=120)
    mock_acompletion = AsyncMock(return_value=mock_resp)
    import src.infrastructure.llm.litellm_adapter as litellm_adapter_mod
    monkeypatch.setattr(litellm_adapter_mod.litellm, "acompletion", mock_acompletion)

    adapter = LiteLLMAdapter()
    req = LLMRequest(
        provider=LLMProvider.ANTHROPIC,
        model="claude-3-5-sonnet-20241022",
        messages=[LLMMessage(role="user", content="Review architecture for Clean Architecture.")],
        max_retries=0,
    )

    resp = await adapter.complete(req)

    assert resp.content == "Claude Architecture Analysis Completed."
    assert resp.provider == LLMProvider.ANTHROPIC
    assert resp.model == "claude-3-5-sonnet-20241022"
    assert resp.usage.total_tokens == 570

    mock_acompletion.assert_called_once()
    call_kwargs = mock_acompletion.call_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-3-5-sonnet-20241022"
    assert call_kwargs["api_key"] == "sk-ant-real-looking-key"


@pytest.mark.asyncio
async def test_litellm_adapter_injects_custom_api_base(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOM_LLM_API_BASE", "https://vllm.internal.corp/v1")
    monkeypatch.setattr(settings, "CUSTOM_LLM_API_KEY", "corp-secret-token")

    mock_resp = _build_mock_response(content="Self-hosted vLLM response.", prompt_tokens=200, completion_tokens=50)
    mock_acompletion = AsyncMock(return_value=mock_resp)
    import src.infrastructure.llm.litellm_adapter as litellm_adapter_mod
    monkeypatch.setattr(litellm_adapter_mod.litellm, "acompletion", mock_acompletion)

    adapter = LiteLLMAdapter()
    req = LLMRequest(
        provider=LLMProvider.CUSTOM,
        model="custom-model",
        messages=[LLMMessage(role="user", content="Ping private server")],
        max_retries=0,
    )

    resp = await adapter.complete(req)

    assert resp.content == "Self-hosted vLLM response."
    call_kwargs = mock_acompletion.call_args.kwargs
    assert call_kwargs["api_base"] == "https://vllm.internal.corp/v1"
    assert call_kwargs["api_key"] == "corp-secret-token"
