"""Tests for nb.core.llm module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nb.config import LLMConfig, LLMModelConfig
from nb.core.llm import (
    ANTHROPIC_API_URL,
    OPENAI_API_URL,
    LLMAPIError,
    LLMClient,
    LLMConfigError,
    LLMRateLimitError,
    LLMResponse,
    Message,
    StreamChunk,
)


class TestMessage:
    """Tests for Message dataclass."""

    def test_create_message(self):
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_create_response(self):
        resp = LLMResponse(
            content="Hello!",
            model="claude-3",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )
        assert resp.content == "Hello!"
        assert resp.model == "claude-3"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5
        assert resp.stop_reason == "end_turn"


class TestStreamChunk:
    """Tests for StreamChunk dataclass."""

    def test_create_chunk(self):
        chunk = StreamChunk(content="Hello", is_final=False)
        assert chunk.content == "Hello"
        assert chunk.is_final is False

    def test_final_chunk(self):
        chunk = StreamChunk(
            content="", is_final=True, input_tokens=100, output_tokens=50
        )
        assert chunk.is_final is True
        assert chunk.input_tokens == 100


class TestLLMClientValidation:
    """Tests for LLMClient configuration validation."""

    def test_missing_api_key_raises(self):
        config = LLMConfig(provider="anthropic", api_key=None)

        with pytest.raises(LLMConfigError, match="No API key configured"):
            LLMClient(config)

    def test_valid_config_creates_client(self):
        config = LLMConfig(provider="anthropic", api_key="test-key")

        client = LLMClient(config)
        assert client.config == config


class TestLLMClientAnthropicRequests:
    """Tests for Anthropic API request building."""

    @pytest.fixture
    def anthropic_client(self):
        config = LLMConfig(
            provider="anthropic",
            api_key="test-key",
            max_tokens=1000,
            temperature=0.5,
        )
        return LLMClient(config)

    def test_build_anthropic_request_headers(self, anthropic_client):
        messages = [Message(role="user", content="Hello")]
        headers, body = anthropic_client._build_anthropic_request(messages, "claude-3")

        assert headers["x-api-key"] == "test-key"
        assert "anthropic-version" in headers
        assert headers["content-type"] == "application/json"

    def test_build_anthropic_request_body(self, anthropic_client):
        messages = [Message(role="user", content="Hello")]
        headers, body = anthropic_client._build_anthropic_request(
            messages, "claude-3", system="Be helpful"
        )

        assert body["model"] == "claude-3"
        assert body["max_tokens"] == 1000
        assert body["temperature"] == 0.5
        # System prompt now includes date/time appended
        assert body["system"].startswith("Be helpful")
        assert "current date and time" in body["system"]
        assert len(body["messages"]) == 1
        assert body["messages"][0]["content"] == "Hello"

    def test_build_anthropic_request_with_stream(self, anthropic_client):
        messages = [Message(role="user", content="Hello")]
        headers, body = anthropic_client._build_anthropic_request(
            messages, "claude-3", stream=True
        )

        assert body["stream"] is True


class TestLLMClientOpenAIRequests:
    """Tests for OpenAI API request building."""

    @pytest.fixture
    def openai_client(self):
        config = LLMConfig(
            provider="openai",
            api_key="test-key",
            max_tokens=1000,
            temperature=0.5,
        )
        return LLMClient(config)

    def test_build_openai_request_headers(self, openai_client):
        messages = [Message(role="user", content="Hello")]
        headers, body = openai_client._build_openai_request(messages, "gpt-4")

        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"

    def test_build_openai_request_body(self, openai_client):
        messages = [Message(role="user", content="Hello")]
        headers, body = openai_client._build_openai_request(
            messages, "gpt-4", system="Be helpful"
        )

        assert body["model"] == "gpt-4"
        assert body["max_tokens"] == 1000
        assert body["temperature"] == 0.5
        # System message should be first
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "Be helpful"
        assert body["messages"][1]["role"] == "user"


class TestLLMClientResponseParsing:
    """Tests for response parsing."""

    @pytest.fixture
    def client(self):
        config = LLMConfig(provider="anthropic", api_key="test-key")
        return LLMClient(config)

    def test_parse_anthropic_response(self, client):
        data = {
            "content": [{"type": "text", "text": "Hello!"}],
            "model": "claude-3",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "stop_reason": "end_turn",
        }

        response = client._parse_anthropic_response(data)

        assert response.content == "Hello!"
        assert response.model == "claude-3"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.stop_reason == "end_turn"

    def test_parse_openai_response(self, client):
        data = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "model": "gpt-4",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        # Temporarily change provider
        client.config = LLMConfig(provider="openai", api_key="test-key")
        response = client._parse_openai_response(data)

        assert response.content == "Hello!"
        assert response.model == "gpt-4"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.stop_reason == "stop"


class TestLLMClientComplete:
    """Tests for the complete method with mocked HTTP."""

    @pytest.fixture
    def client(self):
        config = LLMConfig(
            provider="anthropic",
            api_key="test-key",
            models=LLMModelConfig(smart="claude-3-smart", fast="claude-3-fast"),
        )
        return LLMClient(config)

    def test_complete_uses_smart_model_by_default(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Response"}],
            "model": "claude-3-smart",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = (
                mock_response
            )

            response = client.complete(
                messages=[Message(role="user", content="Hello")],
                use_smart_model=True,
            )

            assert response.content == "Response"
            # Verify the model was used
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            body = call_args.kwargs["json"]
            assert body["model"] == "claude-3-smart"

    def test_complete_uses_fast_model_when_specified(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Response"}],
            "model": "claude-3-fast",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = (
                mock_response
            )

            response = client.complete(
                messages=[Message(role="user", content="Hello")],
                use_smart_model=False,
            )

            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            body = call_args.kwargs["json"]
            assert body["model"] == "claude-3-fast"


class TestLLMClientErrorHandling:
    """Tests for error handling."""

    @pytest.fixture
    def client(self):
        config = LLMConfig(provider="anthropic", api_key="test-key")
        return LLMClient(config)

    def test_rate_limit_error(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}
        mock_response.text = "Rate limit exceeded"

        with pytest.raises(LLMRateLimitError):
            client._handle_error_response(mock_response)

    def test_api_error(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": {"message": "Invalid request"}}
        mock_response.text = "Invalid request"

        with pytest.raises(LLMAPIError) as exc_info:
            client._handle_error_response(mock_response)

        assert exc_info.value.status_code == 400
        assert "Invalid request" in str(exc_info.value)


class TestLLMClientBaseURL:
    """Tests for custom base URL handling."""

    def test_default_anthropic_url(self):
        config = LLMConfig(provider="anthropic", api_key="test-key")
        client = LLMClient(config)

        assert client._get_base_url() == ANTHROPIC_API_URL

    def test_default_openai_url(self):
        config = LLMConfig(provider="openai", api_key="test-key")
        client = LLMClient(config)

        assert client._get_base_url() == OPENAI_API_URL

    def test_custom_base_url(self):
        config = LLMConfig(
            provider="anthropic",
            api_key="test-key",
            base_url="https://custom.api.com",
        )
        client = LLMClient(config)

        assert client._get_base_url() == "https://custom.api.com"
