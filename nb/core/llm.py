"""LLM client abstraction for AI features.

Uses httpx for direct API calls (not SDK) to minimize CLI load time.
Supports Anthropic Claude and OpenAI GPT models.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from nb.config import LLMConfig


# API endpoints
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Anthropic API version
ANTHROPIC_VERSION = "2023-06-01"

# Default timeout for API calls (seconds)
DEFAULT_TIMEOUT = 120.0


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    pass


class LLMConfigError(LLMError):
    """Configuration error (e.g., missing API key)."""

    pass


class LLMAPIError(LLMError):
    """API request error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class LLMRateLimitError(LLMAPIError):
    """Rate limit exceeded."""

    pass


@dataclass
class Message:
    """A message in a conversation."""

    role: str  # "user", "assistant", or "system"
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM API call."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None = None


@dataclass
class StreamChunk:
    """A chunk of streamed response."""

    content: str
    is_final: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMClient:
    """Provider-agnostic LLM client.

    Supports Anthropic Claude and OpenAI GPT models via direct REST API calls.
    Uses httpx for async-capable HTTP requests.
    """

    def __init__(self, config: LLMConfig):
        """Initialize the LLM client.

        Args:
            config: LLM configuration from nb config.

        Raises:
            LLMConfigError: If API key is not configured.
        """
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate the configuration."""
        if not self.config.api_key:
            env_var = (
                "ANTHROPIC_API_KEY"
                if self.config.provider == "anthropic"
                else "OPENAI_API_KEY"
            )
            raise LLMConfigError(
                f"No API key configured. Set {env_var} environment variable "
                f"or configure llm.api_key in nb config."
            )

    def _get_base_url(self) -> str:
        """Get the base URL for API calls."""
        if self.config.base_url:
            return self.config.base_url
        if self.config.provider == "anthropic":
            return ANTHROPIC_API_URL
        return OPENAI_API_URL

    def _build_anthropic_request(
        self,
        messages: list[Message],
        model: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        stream: bool = False,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Build Anthropic API request headers and body."""
        headers = {
            "x-api-key": self.config.api_key or "",
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        # Convert messages to Anthropic format
        anthropic_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]

        body: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or self.config.max_tokens,
        }

        if temperature is not None:
            body["temperature"] = temperature
        elif self.config.temperature is not None:
            body["temperature"] = self.config.temperature

        # Add system prompt
        if system:
            body["system"] = system
        elif self.config.system_prompt:
            body["system"] = self.config.system_prompt

        if stream:
            body["stream"] = True

        return headers, body

    def _build_openai_request(
        self,
        messages: list[Message],
        model: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        stream: bool = False,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Build OpenAI API request headers and body."""
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        # Convert messages to OpenAI format
        openai_messages = []

        # Add system message first
        system_content = system or self.config.system_prompt
        if system_content:
            openai_messages.append({"role": "system", "content": system_content})

        for m in messages:
            if m.role != "system":  # Skip system messages (handled above)
                openai_messages.append({"role": m.role, "content": m.content})

        body: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "max_tokens": max_tokens or self.config.max_tokens,
        }

        if temperature is not None:
            body["temperature"] = temperature
        elif self.config.temperature is not None:
            body["temperature"] = self.config.temperature

        if stream:
            body["stream"] = True

        return headers, body

    def _parse_anthropic_response(self, data: dict[str, Any]) -> LLMResponse:
        """Parse Anthropic API response."""
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=data.get("model", ""),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            stop_reason=data.get("stop_reason"),
        )

    def _parse_openai_response(self, data: dict[str, Any]) -> LLMResponse:
        """Parse OpenAI API response."""
        choices = data.get("choices", [])
        content = ""
        stop_reason = None

        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            stop_reason = choices[0].get("finish_reason")

        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=data.get("model", ""),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            stop_reason=stop_reason,
        )

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Handle error responses from the API."""
        try:
            data = response.json()
            if self.config.provider == "anthropic":
                error = data.get("error", {})
                message = error.get("message", str(data))
            else:
                error = data.get("error", {})
                message = error.get("message", str(data))
        except Exception:
            message = response.text

        if response.status_code == 429:
            raise LLMRateLimitError(f"Rate limit exceeded: {message}", 429)

        raise LLMAPIError(
            f"API error ({response.status_code}): {message}",
            response.status_code,
        )

    def complete(
        self,
        messages: list[Message],
        model: str | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        use_smart_model: bool = True,
    ) -> LLMResponse:
        """Send a completion request to the LLM.

        Args:
            messages: List of conversation messages.
            model: Model to use (overrides config).
            system: System prompt (overrides config).
            max_tokens: Max response tokens (overrides config).
            temperature: Sampling temperature (overrides config).
            use_smart_model: If True and model not specified, use smart model.
                           If False, use fast model.

        Returns:
            LLMResponse with the generated content and metadata.

        Raises:
            LLMAPIError: If the API request fails.
        """
        if model is None:
            model = (
                self.config.models.smart if use_smart_model else self.config.models.fast
            )

        url = self._get_base_url()

        if self.config.provider == "anthropic":
            headers, body = self._build_anthropic_request(
                messages, model, system, max_tokens, temperature
            )
        else:
            headers, body = self._build_openai_request(
                messages, model, system, max_tokens, temperature
            )

        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            response = client.post(url, headers=headers, json=body)

        if response.status_code != 200:
            self._handle_error_response(response)

        data = response.json()

        if self.config.provider == "anthropic":
            return self._parse_anthropic_response(data)
        return self._parse_openai_response(data)

    def complete_stream(
        self,
        messages: list[Message],
        model: str | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        use_smart_model: bool = True,
    ) -> Iterator[StreamChunk]:
        """Send a streaming completion request to the LLM.

        Args:
            messages: List of conversation messages.
            model: Model to use (overrides config).
            system: System prompt (overrides config).
            max_tokens: Max response tokens (overrides config).
            temperature: Sampling temperature (overrides config).
            use_smart_model: If True and model not specified, use smart model.

        Yields:
            StreamChunk objects with content and metadata.

        Raises:
            LLMAPIError: If the API request fails.
        """
        if model is None:
            model = (
                self.config.models.smart if use_smart_model else self.config.models.fast
            )

        url = self._get_base_url()

        if self.config.provider == "anthropic":
            headers, body = self._build_anthropic_request(
                messages, model, system, max_tokens, temperature, stream=True
            )
        else:
            headers, body = self._build_openai_request(
                messages, model, system, max_tokens, temperature, stream=True
            )

        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code != 200:
                    # Read the full response for error handling
                    response.read()
                    self._handle_error_response(response)

                if self.config.provider == "anthropic":
                    yield from self._parse_anthropic_stream(response)
                else:
                    yield from self._parse_openai_stream(response)

    def _parse_anthropic_stream(
        self, response: httpx.Response
    ) -> Iterator[StreamChunk]:
        """Parse streaming response from Anthropic API."""
        input_tokens = 0
        output_tokens = 0

        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            data_str = line[6:]  # Remove "data: " prefix
            if data_str == "[DONE]":
                break

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            event_type = data.get("type", "")

            if event_type == "message_start":
                usage = data.get("message", {}).get("usage", {})
                input_tokens = usage.get("input_tokens", 0)

            elif event_type == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        yield StreamChunk(content=text)

            elif event_type == "message_delta":
                usage = data.get("usage", {})
                output_tokens = usage.get("output_tokens", 0)

            elif event_type == "message_stop":
                yield StreamChunk(
                    content="",
                    is_final=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

    def _parse_openai_stream(self, response: httpx.Response) -> Iterator[StreamChunk]:
        """Parse streaming response from OpenAI API."""
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            data_str = line[6:]  # Remove "data: " prefix
            if data_str == "[DONE]":
                yield StreamChunk(content="", is_final=True)
                break

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            choices = data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield StreamChunk(content=content)


# Convenience functions


def get_llm_client() -> LLMClient:
    """Get an LLM client using the global config.

    Returns:
        Configured LLMClient instance.

    Raises:
        LLMConfigError: If LLM is not properly configured.
    """
    from nb.config import get_config

    config = get_config()
    return LLMClient(config.llm)


def quick_complete(
    prompt: str,
    system: str | None = None,
    use_smart_model: bool = False,
) -> str:
    """Quick helper for single-turn completions.

    Args:
        prompt: The user prompt.
        system: Optional system prompt.
        use_smart_model: If True, use smart model. Default is fast model.

    Returns:
        The LLM response content.
    """
    client = get_llm_client()
    response = client.complete(
        messages=[Message(role="user", content=prompt)],
        system=system,
        use_smart_model=use_smart_model,
    )
    return response.content
