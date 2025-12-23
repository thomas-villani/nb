"""Configuration parsing functions for nb."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .models import (
    DEFAULT_NOTES_ROOT,
    ClipConfig,
    EmbeddingsConfig,
    GitConfig,
    InboxConfig,
    KanbanBoardConfig,
    KanbanColumnConfig,
    LLMConfig,
    LLMModelConfig,
    NotebookConfig,
    RaindropConfig,
    RecorderConfig,
    SearchConfig,
    TodoConfig,
    TodoViewConfig,
)


def expand_path(path: str | Path) -> Path:
    """Expand ~ and environment variables in a path."""
    path_str = str(path)
    # Expand environment variables
    path_str = os.path.expandvars(path_str)
    # Expand ~
    return Path(path_str).expanduser()


def get_default_notes_root() -> Path:
    """Get the default notes root directory."""
    # Check environment variable first
    env_root = os.environ.get("NB_NOTES_ROOT")
    if env_root:
        return expand_path(env_root)
    return DEFAULT_NOTES_ROOT


def get_config_path(notes_root: Path | None = None) -> Path:
    """Get the path to the config file."""
    if notes_root is None:
        notes_root = get_default_notes_root()
    return notes_root / ".nb" / "config.yaml"


def _parse_notebooks(data: list[Any]) -> list[NotebookConfig]:
    """Parse notebooks configuration.

    Supports both old format (list of strings) and new format (list of dicts).
    External notebooks can specify a path outside notes_root.
    """
    result = []
    for item in data:
        if isinstance(item, str):
            # Old format: just a string name
            # "daily" is date-based by default for backwards compatibility
            result.append(NotebookConfig(name=item, date_based=(item == "daily")))
        elif isinstance(item, dict):
            # New format: dict with name and optional settings
            ext_path = None
            if "path" in item:
                ext_path = expand_path(item["path"])
            result.append(
                NotebookConfig(
                    name=item["name"],
                    date_based=item.get("date_based", False),
                    todo_exclude=item.get("todo_exclude", False),
                    path=ext_path,
                    color=item.get("color"),
                    icon=item.get("icon"),
                    template=item.get("template"),
                )
            )
    return result


def _parse_embeddings(data: dict[str, Any] | None) -> EmbeddingsConfig:
    """Parse embeddings configuration.

    API key is loaded from OPENAI_API_KEY environment variable when using OpenAI provider.
    """
    if data is None:
        data = {}

    provider = data.get("provider", "ollama")

    # Get API key from environment variable (only needed for OpenAI)
    api_key = None
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")

    return EmbeddingsConfig(
        provider=provider,
        model=data.get("model", "nomic-embed-text"),
        base_url=data.get("base_url"),
        api_key=api_key,
        chunk_size=data.get("chunk_size", 500),
        chunking_method=data.get("chunking_method", "paragraphs"),
    )


def _parse_todo_views(data: list[dict[str, Any]]) -> list[TodoViewConfig]:
    """Parse todo_views configuration."""
    result = []
    for item in data:
        result.append(
            TodoViewConfig(
                name=item["name"],
                filters=item.get("filters", {}),
            )
        )
    return result


def _parse_kanban_columns(data: list[dict[str, Any]]) -> list[KanbanColumnConfig]:
    """Parse kanban column configuration."""
    result = []
    for item in data:
        result.append(
            KanbanColumnConfig(
                name=item["name"],
                filters=item.get("filters", {}),
                color=item.get("color", "white"),
            )
        )
    return result


def _parse_kanban_boards(data: list[dict[str, Any]]) -> list[KanbanBoardConfig]:
    """Parse kanban_boards configuration."""
    result = []
    for item in data:
        columns = _parse_kanban_columns(item.get("columns", []))
        result.append(
            KanbanBoardConfig(
                name=item["name"],
                columns=columns,
            )
        )
    return result


def _parse_search(data: dict[str, Any] | None) -> SearchConfig:
    """Parse search configuration.

    Serper API key is loaded from SERPER_API_KEY environment variable.
    """
    if data is None:
        data = {}

    return SearchConfig(
        vector_weight=data.get("vector_weight", 0.7),
        score_threshold=data.get("score_threshold", 0.4),
        recency_decay_days=data.get("recency_decay_days", 30),
        serper_api_key=os.environ.get("SERPER_API_KEY"),
    )


def _parse_todo_config(data: dict[str, Any] | None) -> TodoConfig:
    """Parse todo configuration."""
    if data is None:
        return TodoConfig()
    return TodoConfig(
        default_sort=data.get("default_sort", "source"),
        inbox_file=data.get("inbox_file", "todo.md"),
        auto_complete_children=data.get("auto_complete_children", True),
    )


def _parse_recorder_config(data: dict[str, Any] | None) -> RecorderConfig:
    """Parse recorder configuration.

    Deepgram API key is loaded from DEEPGRAM_API_KEY environment variable.
    """
    if data is None:
        data = {}

    return RecorderConfig(
        mic_device=data.get("mic_device"),
        loopback_device=data.get("loopback_device"),
        sample_rate=data.get("sample_rate", 16000),
        auto_delete_audio=data.get("auto_delete_audio", False),
        transcribe_timeout=data.get("transcribe_timeout", 600),
        mic_speaker_label=data.get("mic_speaker_label", "You"),
        deepgram_api_key=os.environ.get("DEEPGRAM_API_KEY"),
    )


def _parse_clip_config(data: dict[str, Any] | None) -> ClipConfig:
    """Parse clip configuration."""
    if data is None:
        return ClipConfig()
    return ClipConfig(
        user_agent=data.get("user_agent", "nb-web-clipper/1.0"),
        timeout=data.get("timeout", 30),
        auto_tag_domain=data.get("auto_tag_domain", True),
    )


def _parse_raindrop_config(data: dict[str, Any] | None) -> RaindropConfig:
    """Parse Raindrop configuration.

    API token is loaded from RAINDROP_API_KEY environment variable.
    """
    if data is None:
        data = {}

    return RaindropConfig(
        collection=data.get("collection", "nb-inbox"),
        auto_archive=data.get("auto_archive", True),
        api_token=os.environ.get("RAINDROP_API_KEY"),
    )


def _parse_inbox_config(data: dict[str, Any] | None) -> InboxConfig:
    """Parse inbox configuration."""
    if data is None:
        return InboxConfig()
    return InboxConfig(
        source=data.get("source", "raindrop"),
        default_notebook=data.get("default_notebook", "bookmarks"),
        auto_summarize=data.get("auto_summarize", True),
        raindrop=_parse_raindrop_config(data.get("raindrop")),
    )


def _parse_git_config(data: dict[str, Any] | None) -> GitConfig:
    """Parse git configuration."""
    if data is None:
        return GitConfig()
    return GitConfig(
        enabled=data.get("enabled", False),
        auto_commit=data.get("auto_commit", True),
        commit_message_template=data.get("commit_message_template", "Update {path}"),
    )


def _parse_llm_models_config(data: dict[str, Any] | None) -> LLMModelConfig:
    """Parse LLM models configuration."""
    if data is None:
        return LLMModelConfig()
    return LLMModelConfig(
        smart=data.get("smart", "claude-sonnet-4-5"),
        fast=data.get("fast", "claude-haiku-4-5"),
    )


def _parse_llm_config(data: dict[str, Any] | None) -> LLMConfig:
    """Parse LLM configuration.

    API key is loaded from environment variable:
    - ANTHROPIC_API_KEY for Anthropic provider
    - OPENAI_API_KEY for OpenAI provider
    """
    if data is None:
        data = {}

    provider = data.get("provider", "anthropic")

    # Get API key from environment variable based on provider
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
    else:
        api_key = None

    return LLMConfig(
        provider=provider,
        models=_parse_llm_models_config(data.get("models")),
        api_key=api_key,
        base_url=data.get("base_url"),
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature", 0.7),
        system_prompt=data.get("system_prompt"),
    )
