"""Contract tests for LLM API integrations.

These tests call real APIs and validate that our client code works correctly
with actual API responses. They require API keys to be set in the environment.

Run with: pytest -m contract tests/test_contract_llm.py

## Handling Non-Determinacy

AI responses can vary even with temperature=0.0. These tests are designed to be
resilient by:
1. Using temperature=0.0 for maximum determinism
2. Using simple, unambiguous prompts that constrain possible responses
3. Asserting on response STRUCTURE (has content, has tokens) not exact content
4. When checking content, using flexible assertions (contains, not equals)
5. Allowing alternative valid responses (e.g., tool call OR text response)

If a test fails intermittently, the assertion should be made more flexible,
NOT the test removed.
"""

from __future__ import annotations

# Import skip conditions from conftest (pytest makes conftest available without prefix)
import os

import pytest

from nb.config import LLMConfig, LLMModelConfig
from nb.core.llm import LLMClient, Message, ToolDefinition

requires_anthropic_key = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="requires ANTHROPIC_API_KEY environment variable",
)

requires_openai_key = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="requires OPENAI_API_KEY environment variable",
)


@pytest.mark.contract
@requires_anthropic_key
class TestAnthropicContract:
    """Contract tests for Anthropic Claude API."""

    @pytest.fixture
    def client(self):
        config = LLMConfig(
            provider="anthropic",
            api_key=None,  # Will be loaded from environment
            max_tokens=100,
            temperature=0.0,  # Deterministic for testing
            models=LLMModelConfig(
                smart="claude-sonnet-4-20250514",
                fast="claude-haiku-3-5-20241022",
            ),
        )
        return LLMClient(config)

    def test_complete_returns_valid_response(self, client):
        """Verify basic completion works and returns expected structure."""
        messages = [Message(role="user", content="Say 'hello' and nothing else.")]

        response = client.complete(messages, use_smart_model=False)

        assert response.content is not None
        assert len(response.content) > 0
        assert "hello" in response.content.lower()
        assert response.model is not None
        assert response.input_tokens > 0
        assert response.output_tokens > 0
        assert response.stop_reason in ("end_turn", "stop")

    def test_complete_with_system_prompt(self, client):
        """Verify system prompts are respected."""
        # Use a very explicit prompt that constrains the response
        messages = [
            Message(
                role="user", content="What is your name? Reply with just your name."
            )
        ]

        response = client.complete(
            messages,
            system="You are a robot named Beep. Your name is Beep. Always respond as Beep.",
            use_smart_model=False,
        )

        assert response.content is not None
        # The model should mention "Beep" somewhere in response
        assert (
            "beep" in response.content.lower()
        ), f"Expected 'beep' in: {response.content}"

    def test_streaming_yields_chunks(self, client):
        """Verify streaming produces valid chunks."""
        messages = [Message(role="user", content="Count from 1 to 3.")]

        chunks = list(client.complete_stream(messages, use_smart_model=False))

        assert len(chunks) > 0

        # Should have content chunks
        content_chunks = [c for c in chunks if c.content]
        assert len(content_chunks) > 0

        # Last chunk should be final
        assert chunks[-1].is_final

        # Final chunk should have token counts
        assert chunks[-1].input_tokens is not None
        assert chunks[-1].output_tokens is not None

    def test_tool_calling_works(self, client):
        """Verify tool calling produces valid tool calls."""
        tools = [
            ToolDefinition(
                name="get_weather",
                description="Get the current weather for a location",
                parameters={
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city name",
                        }
                    },
                    "required": ["location"],
                },
            )
        ]

        messages = [Message(role="user", content="What's the weather in Paris?")]

        response = client.complete(messages, tools=tools, use_smart_model=False)

        # Should either have tool calls or a text response
        assert response.content is not None or response.tool_calls is not None

        if response.tool_calls:
            assert len(response.tool_calls) > 0
            tool_call = response.tool_calls[0]
            assert tool_call.name == "get_weather"
            assert "location" in tool_call.arguments
            assert response.stop_reason == "tool_use"


@pytest.mark.contract
@requires_openai_key
class TestOpenAIContract:
    """Contract tests for OpenAI GPT API."""

    @pytest.fixture
    def client(self):
        config = LLMConfig(
            provider="openai",
            api_key=None,  # Will be loaded from environment
            max_tokens=100,
            temperature=0.0,  # Deterministic for testing
            models=LLMModelConfig(
                smart="gpt-4o",
                fast="gpt-4o-mini",
            ),
        )
        return LLMClient(config)

    def test_complete_returns_valid_response(self, client):
        """Verify basic completion works and returns expected structure."""
        messages = [Message(role="user", content="Say 'hello' and nothing else.")]

        response = client.complete(messages, use_smart_model=False)

        assert response.content is not None
        assert len(response.content) > 0
        assert "hello" in response.content.lower()
        assert response.model is not None
        assert response.input_tokens > 0
        assert response.output_tokens > 0
        assert response.stop_reason in ("stop", "length")

    def test_complete_with_system_prompt(self, client):
        """Verify system prompts are respected."""
        # Use a very explicit prompt that constrains the response
        messages = [
            Message(
                role="user", content="What is your name? Reply with just your name."
            )
        ]

        response = client.complete(
            messages,
            system="You are a robot named Beep. Your name is Beep. Always respond as Beep.",
            use_smart_model=False,
        )

        assert response.content is not None
        # The model should mention "Beep" somewhere in response
        assert (
            "beep" in response.content.lower()
        ), f"Expected 'beep' in: {response.content}"

    def test_streaming_yields_chunks(self, client):
        """Verify streaming produces valid chunks."""
        messages = [Message(role="user", content="Count from 1 to 3.")]

        chunks = list(client.complete_stream(messages, use_smart_model=False))

        assert len(chunks) > 0

        # Should have content chunks
        content_chunks = [c for c in chunks if c.content]
        assert len(content_chunks) > 0

        # Last chunk should be final
        assert chunks[-1].is_final
