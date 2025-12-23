"""Configuration utility functions for nb."""

from __future__ import annotations

from typing import Any

from .parsers import expand_path

# Configurable settings with descriptions
# Note: API keys are NOT configurable via config - use environment variables instead
CONFIGURABLE_SETTINGS = {
    "editor": "Text editor command (e.g., code, vim, micro)",
    "env_file": "Custom .env file path for API keys (default: .nb/.env)",
    "date_format": "Date display format (e.g., %Y-%m-%d)",
    "time_format": "Time display format (e.g., %H:%M)",
    "daily_title_format": "Daily note title format (e.g., %A, %B %d, %Y)",
    "week_start_day": "First day of week (monday or sunday)",
    "embeddings.provider": "Embeddings provider (ollama or openai)",
    "embeddings.model": "Embeddings model name (e.g., nomic-embed-text)",
    "embeddings.base_url": "Custom embeddings API endpoint URL",
    "embeddings.chunk_size": "Max tokens per chunk (e.g., 500)",
    "embeddings.chunking_method": "Chunking method (sentences, tokens, paragraphs, sections)",
    "search.vector_weight": "Hybrid search balance: 0=keyword, 1=vector (default 0.7)",
    "search.score_threshold": "Minimum score to show search results (default 0.4)",
    "search.recency_decay_days": "Half-life in days for recency boost (default 30)",
    "todo.default_sort": "Default sort order (source, tag, priority, created)",
    "todo.inbox_file": "Name of inbox file in notes_root (default todo.md)",
    "todo.auto_complete_children": "Complete subtasks when parent done (true/false)",
    "recorder.mic_speaker_label": "Label for microphone speaker in transcripts (default: You)",
    "clip.user_agent": "User-Agent header for web clipping requests",
    "clip.timeout": "Request timeout in seconds (default 30)",
    "clip.auto_tag_domain": "Auto-tag clipped content with source domain (true/false)",
    "inbox.source": "Inbox source service (currently only 'raindrop')",
    "inbox.default_notebook": "Default notebook for clipped items (default: bookmarks)",
    "inbox.auto_summarize": "Auto-generate AI summary when clipping (true/false, default: true)",
    "inbox.raindrop.collection": "Raindrop collection to pull from (default: nb-inbox)",
    "inbox.raindrop.auto_archive": "Move items to archive after clipping (true/false)",
    "git.enabled": "Enable git integration (true/false)",
    "git.auto_commit": "Auto-commit after note changes (true/false)",
    "git.commit_message_template": "Commit message template (supports {path}, {notebook}, {title}, {date})",
    "llm.provider": "LLM provider (anthropic or openai)",
    "llm.models.smart": "Model for complex tasks (e.g., claude-sonnet-4-5)",
    "llm.models.fast": "Model for simple tasks (e.g., claude-haiku-4-5)",
    "llm.base_url": "Custom API endpoint URL (for proxies)",
    "llm.max_tokens": "Max tokens in LLM response (default 4096)",
    "llm.temperature": "Sampling temperature (0.0-1.0, default 0.7)",
    "llm.system_prompt": "Global system prompt for AI commands",
}

# Notebook-specific settings (accessed via notebook.<name>.<setting>)
NOTEBOOK_SETTINGS = {
    "color": "Display color (e.g., blue, green, #ff5500)",
    "icon": "Display icon/emoji (e.g., 📝, 🔧, or name like 'wrench')",
    "date_based": "Use date-based organization (true/false)",
    "todo_exclude": "Exclude from nb todo by default (true/false)",
    "template": "Default template name for new notes",
}

# Map of emoji names to emoji characters for convenient CLI input
EMOJI_ALIASES = {
    # Common icons
    "calendar": "📅",
    "note": "📝",
    "notes": "📝",
    "book": "📕",
    "books": "📚",
    "folder": "📁",
    "file": "📄",
    # Tools
    "wrench": "🔧",
    "hammer": "🔨",
    "gear": "⚙️",
    "tools": "🛠️",
    # Status
    "star": "⭐",
    "check": "✅",
    "pin": "📌",
    "flag": "🚩",
    "bell": "🔔",
    # Categories
    "work": "💼",
    "home": "🏠",
    "personal": "👤",
    "idea": "💡",
    "bulb": "💡",
    # Activities
    "code": "💻",
    "computer": "💻",
    "rocket": "🚀",
    "target": "🎯",
    "brain": "🧠",
    # Nature/misc
    "sun": "☀️",
    "moon": "🌙",
    "fire": "🔥",
    "heart": "❤️",
    "sparkle": "✨",
}


def resolve_emoji(value: str) -> str:
    """Resolve an emoji alias to its character, or return as-is.

    Args:
        value: Either an emoji character or an alias name

    Returns:
        The emoji character (resolved from alias if applicable)

    """
    return EMOJI_ALIASES.get(value.lower(), value)


# Valid boolean string values
BOOL_TRUE_VALUES = ("true", "1", "yes", "on")
BOOL_FALSE_VALUES = ("false", "0", "no", "off")


def parse_bool_strict(value: str, setting_name: str) -> bool:
    """Parse a boolean string value strictly.

    Args:
        value: String value to parse (e.g., "true", "false", "1", "0")
        setting_name: Name of the setting (for error messages)

    Returns:
        Boolean value

    Raises:
        ValueError: If the value is not a recognized boolean string

    """
    lower = value.lower()
    if lower in BOOL_TRUE_VALUES:
        return True
    if lower in BOOL_FALSE_VALUES:
        return False
    valid = ", ".join(BOOL_TRUE_VALUES + BOOL_FALSE_VALUES)
    raise ValueError(
        f"Invalid boolean value '{value}' for {setting_name}. Valid: {valid}"
    )


# Valid Rich color names (standard + bright variants)
VALID_COLORS = {
    # Standard colors
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    # Bright variants
    "bright_black",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "bright_white",
    # Common aliases
    "grey",
    "gray",
    "purple",
    "orange",
    "pink",
}


def is_valid_color(color: str) -> bool:
    """Check if a color value is valid for Rich.

    Accepts:
    - Named colors (red, blue, cyan, etc.)
    - Hex colors (#ff5500, #f50)
    - RGB notation (rgb(255,85,0))

    """
    color_lower = color.lower()

    # Named color
    if color_lower in VALID_COLORS:
        return True

    # Hex color (#RGB or #RRGGBB)
    if color.startswith("#"):
        hex_part = color[1:]
        if len(hex_part) in (3, 6):
            try:
                int(hex_part, 16)
                return True
            except ValueError:
                pass

    # RGB notation
    if color_lower.startswith("rgb(") and color_lower.endswith(")"):
        return True  # Let Rich validate the exact format

    return False


def get_config_value(key: str) -> Any:
    """Get a config value by dot-notation key.

    Args:
        key: Configuration key (e.g., 'editor', 'embeddings.provider',
             'notebook.daily.color')

    Returns:
        The configuration value, or None if not found.

    """
    # Import here to avoid circular imports
    from . import get_config

    config = get_config()
    parts = key.split(".")

    if len(parts) == 1:
        # Top-level setting
        if key == "editor":
            return config.editor
        elif key == "env_file":
            return str(config.env_file) if config.env_file else None
        elif key == "date_format":
            return config.date_format
        elif key == "time_format":
            return config.time_format
        elif key == "daily_title_format":
            return config.daily_title_format
        elif key == "week_start_day":
            return config.week_start_day
        elif key == "notes_root":
            return str(config.notes_root)
    elif parts[0] == "embeddings" and len(parts) == 2:
        # Embeddings setting
        attr = parts[1]
        if hasattr(config.embeddings, attr):
            return getattr(config.embeddings, attr)
    elif parts[0] == "search" and len(parts) == 2:
        # Search setting
        attr = parts[1]
        if hasattr(config.search, attr):
            return getattr(config.search, attr)
    elif parts[0] == "todo" and len(parts) == 2:
        # Todo setting
        attr = parts[1]
        if hasattr(config.todo, attr):
            return getattr(config.todo, attr)
    elif parts[0] == "recorder" and len(parts) == 2:
        # Recorder setting
        attr = parts[1]
        if hasattr(config.recorder, attr):
            return getattr(config.recorder, attr)
    elif parts[0] == "clip" and len(parts) == 2:
        # Clip setting
        attr = parts[1]
        if hasattr(config.clip, attr):
            return getattr(config.clip, attr)
    elif parts[0] == "inbox" and len(parts) == 2:
        # Inbox setting (source, default_notebook, auto_summarize)
        attr = parts[1]
        if attr in ("source", "default_notebook", "auto_summarize"):
            return getattr(config.inbox, attr)
    elif parts[0] == "inbox" and len(parts) == 3 and parts[1] == "raindrop":
        # Inbox raindrop setting: inbox.raindrop.<attr>
        attr = parts[2]
        if hasattr(config.inbox.raindrop, attr):
            return getattr(config.inbox.raindrop, attr)
    elif parts[0] == "git" and len(parts) == 2:
        # Git setting
        attr = parts[1]
        if hasattr(config.git, attr):
            return getattr(config.git, attr)
    elif parts[0] == "llm" and len(parts) == 2:
        # LLM setting
        attr = parts[1]
        if hasattr(config.llm, attr):
            return getattr(config.llm, attr)
    elif parts[0] == "llm" and len(parts) == 3 and parts[1] == "models":
        # LLM models setting: llm.models.<attr>
        attr = parts[2]
        if hasattr(config.llm.models, attr):
            return getattr(config.llm.models, attr)
    elif parts[0] == "notebook" and len(parts) == 3:
        # Notebook-specific setting: notebook.<name>.<setting>
        nb_name, setting = parts[1], parts[2]
        nb = config.get_notebook(nb_name)
        if nb is not None and setting in NOTEBOOK_SETTINGS:
            return getattr(nb, setting, None)

    return None


def set_config_value(key: str, value: str) -> bool:
    """Set a config value by dot-notation key.

    Args:
        key: Configuration key (e.g., 'editor', 'embeddings.provider',
             'notebook.daily.color')
        value: Value to set (use empty string or 'none' to clear)

    Returns:
        True if successful, False if key not recognized.

    Raises:
        ValueError: If the value is invalid for the setting type.

    """
    # Import here to avoid circular imports
    from . import get_config, reset_config
    from .io import save_config

    config = get_config()
    parts = key.split(".")

    if len(parts) == 1:
        # Top-level setting
        if key == "editor":
            config.editor = value
        elif key == "env_file":
            if value.lower() in ("", "none"):
                config.env_file = None
            else:
                config.env_file = expand_path(value)
        elif key == "date_format":
            config.date_format = value
        elif key == "time_format":
            config.time_format = value
        elif key == "daily_title_format":
            config.daily_title_format = value
        elif key == "week_start_day":
            valid_days = ("monday", "sunday")
            if value.lower() not in valid_days:
                raise ValueError(
                    f"week_start_day must be one of: {', '.join(valid_days)}"
                )
            config.week_start_day = value.lower()
        else:
            return False
    elif parts[0] == "embeddings" and len(parts) == 2:
        # Embeddings setting (api_key not configurable - use env var)
        attr = parts[1]
        if attr in ("provider", "model", "base_url"):
            setattr(config.embeddings, attr, value if value else None)
        elif attr == "chunk_size":
            try:
                config.embeddings.chunk_size = int(value)
            except ValueError:
                raise ValueError(
                    f"chunk_size must be an integer, got '{value}'"
                ) from None
        elif attr == "chunking_method":
            valid_methods = ("sentences", "tokens", "paragraphs", "sections")
            if value not in valid_methods:
                raise ValueError(
                    f"chunking_method must be one of: {', '.join(valid_methods)}"
                )
            config.embeddings.chunking_method = value
        else:
            return False
    elif parts[0] == "search" and len(parts) == 2:
        # Search setting
        attr = parts[1]
        if attr == "vector_weight":
            try:
                weight = float(value)
                if not 0 <= weight <= 1:
                    raise ValueError("vector_weight must be between 0 and 1")
                config.search.vector_weight = weight
            except ValueError as e:
                if "could not convert" in str(e).lower():
                    raise ValueError(
                        f"vector_weight must be a number, got '{value}'"
                    ) from None
                raise
        elif attr == "score_threshold":
            try:
                threshold = float(value)
                if not 0 <= threshold <= 1:
                    raise ValueError("score_threshold must be between 0 and 1")
                config.search.score_threshold = threshold
            except ValueError as e:
                if "could not convert" in str(e).lower():
                    raise ValueError(
                        f"score_threshold must be a number, got '{value}'"
                    ) from None
                raise
        elif attr == "recency_decay_days":
            try:
                days = int(value)
                if days < 1:
                    raise ValueError("recency_decay_days must be at least 1")
                config.search.recency_decay_days = days
            except ValueError as e:
                if "invalid literal" in str(e).lower():
                    raise ValueError(
                        f"recency_decay_days must be an integer, got '{value}'"
                    ) from None
                raise
        else:
            return False
    elif parts[0] == "todo" and len(parts) == 2:
        # Todo setting
        attr = parts[1]
        if attr == "default_sort":
            valid_sorts = ("source", "tag", "priority", "created")
            if value not in valid_sorts:
                raise ValueError(
                    f"default_sort must be one of: {', '.join(valid_sorts)}"
                )
            config.todo.default_sort = value
        elif attr == "inbox_file":
            config.todo.inbox_file = value
        elif attr == "auto_complete_children":
            config.todo.auto_complete_children = parse_bool_strict(
                value, "todo.auto_complete_children"
            )
        else:
            return False
    elif parts[0] == "recorder" and len(parts) == 2:
        # Recorder setting (deepgram_api_key not configurable - use env var)
        attr = parts[1]
        if attr == "mic_speaker_label":
            config.recorder.mic_speaker_label = value if value else "You"
        else:
            return False
    elif parts[0] == "clip" and len(parts) == 2:
        # Clip setting
        attr = parts[1]
        if attr == "user_agent":
            config.clip.user_agent = value if value else "nb-web-clipper/1.0"
        elif attr == "timeout":
            try:
                timeout = int(value)
                if timeout < 1:
                    raise ValueError("timeout must be at least 1 second")
                config.clip.timeout = timeout
            except ValueError as e:
                if "invalid literal" in str(e).lower():
                    raise ValueError(
                        f"timeout must be an integer, got '{value}'"
                    ) from None
                raise
        elif attr == "auto_tag_domain":
            config.clip.auto_tag_domain = parse_bool_strict(
                value, "clip.auto_tag_domain"
            )
        else:
            return False
    elif parts[0] == "inbox" and len(parts) == 2:
        # Inbox setting
        attr = parts[1]
        if attr == "source":
            valid_sources = ("raindrop",)
            if value not in valid_sources:
                raise ValueError(f"source must be one of: {', '.join(valid_sources)}")
            config.inbox.source = value
        elif attr == "default_notebook":
            config.inbox.default_notebook = value if value else "bookmarks"
        elif attr == "auto_summarize":
            config.inbox.auto_summarize = parse_bool_strict(
                value, "inbox.auto_summarize"
            )
        else:
            return False
    elif parts[0] == "inbox" and len(parts) == 3 and parts[1] == "raindrop":
        # Inbox raindrop setting: inbox.raindrop.<attr>
        attr = parts[2]
        if attr == "collection":
            config.inbox.raindrop.collection = value if value else "nb-inbox"
        elif attr == "auto_archive":
            config.inbox.raindrop.auto_archive = parse_bool_strict(
                value, "inbox.raindrop.auto_archive"
            )
        else:
            return False
    elif parts[0] == "git" and len(parts) == 2:
        # Git setting
        attr = parts[1]
        if attr == "enabled":
            config.git.enabled = parse_bool_strict(value, "git.enabled")
        elif attr == "auto_commit":
            config.git.auto_commit = parse_bool_strict(value, "git.auto_commit")
        elif attr == "commit_message_template":
            config.git.commit_message_template = value if value else "Update {path}"
        else:
            return False
    elif parts[0] == "llm" and len(parts) == 2:
        # LLM setting
        attr = parts[1]
        if attr == "provider":
            valid_providers = ("anthropic", "openai")
            if value not in valid_providers:
                raise ValueError(
                    f"llm.provider must be one of: {', '.join(valid_providers)}"
                )
            config.llm.provider = value
        elif attr == "base_url":
            config.llm.base_url = value if value else None
        elif attr == "max_tokens":
            try:
                tokens = int(value)
                if tokens < 1:
                    raise ValueError("max_tokens must be at least 1")
                config.llm.max_tokens = tokens
            except ValueError as e:
                if "invalid literal" in str(e).lower():
                    raise ValueError(
                        f"max_tokens must be an integer, got '{value}'"
                    ) from None
                raise
        elif attr == "temperature":
            try:
                temp = float(value)
                if not 0 <= temp <= 2:
                    raise ValueError("temperature must be between 0 and 2")
                config.llm.temperature = temp
            except ValueError as e:
                if "could not convert" in str(e).lower():
                    raise ValueError(
                        f"temperature must be a number, got '{value}'"
                    ) from None
                raise
        elif attr == "system_prompt":
            config.llm.system_prompt = value if value else None
        else:
            return False
    elif parts[0] == "llm" and len(parts) == 3 and parts[1] == "models":
        # LLM models setting: llm.models.<attr>
        attr = parts[2]
        if attr == "smart":
            config.llm.models.smart = value
        elif attr == "fast":
            config.llm.models.fast = value
        else:
            return False
    elif parts[0] == "notebook" and len(parts) == 3:
        # Notebook-specific setting: notebook.<name>.<setting>
        nb_name, setting = parts[1], parts[2]
        nb = config.get_notebook(nb_name)
        if nb is None:
            raise ValueError(f"Notebook '{nb_name}' not found")
        if setting not in NOTEBOOK_SETTINGS:
            return False

        # Handle boolean settings
        if setting in ("date_based", "todo_exclude"):
            bool_value = parse_bool_strict(value, f"notebook.{nb_name}.{setting}")
            setattr(nb, setting, bool_value)
        elif setting == "color":
            # Validate and set color
            if value.lower() in ("", "none"):
                nb.color = None
            elif is_valid_color(value):
                nb.color = value
            else:
                valid = ", ".join(sorted(VALID_COLORS)[:10]) + ", ... or #hex"
                raise ValueError(f"Invalid color '{value}'. Valid: {valid}")
        elif setting == "icon":
            # Resolve emoji alias and set
            if value.lower() in ("", "none"):
                nb.icon = None
            else:
                nb.icon = resolve_emoji(value)
        elif setting == "template":
            # Set default template name
            if value.lower() in ("", "none"):
                nb.template = None
            else:
                nb.template = value
    else:
        return False

    save_config(config)
    reset_config()  # Clear cache to reload with new values
    return True


def list_config_settings() -> dict[str, tuple[str, Any]]:
    """List all configurable settings with their current values.

    Returns:
        Dict mapping key to (description, current_value).

    """
    # Import here to avoid circular imports
    from . import get_config

    result = {}
    for key, description in CONFIGURABLE_SETTINGS.items():
        value = get_config_value(key)
        result[key] = (description, value)

    # Add notebook-specific settings
    config = get_config()
    for nb in config.notebooks:
        for setting, description in NOTEBOOK_SETTINGS.items():
            key = f"notebook.{nb.name}.{setting}"
            value = getattr(nb, setting, None)
            result[key] = (description, value)

    return result
