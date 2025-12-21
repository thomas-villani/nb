"""Note summarization with AI.

Provides single-note and multi-note (map-reduce) summarization
with support for frontmatter updates and output to notes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import frontmatter

from nb.config import get_config
from nb.core.llm import Message, StreamChunk, get_llm_client
from nb.core.notes import (
    ensure_daily_note,
    get_daily_note_path,
    list_notebook_notes_by_date,
    list_notes,
)
from nb.utils.dates import parse_fuzzy_date

if TYPE_CHECKING:
    pass


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class NoteSource:
    """A note to be summarized."""

    path: Path
    title: str | None
    content: str
    date: date | None
    notebook: str | None
    tags: list[str] = field(default_factory=list)


@dataclass
class NoteSummary:
    """Summary of a single note."""

    path: Path
    title: str | None
    summary: str
    notebook: str | None = None


@dataclass
class SummarizeResult:
    """Result from summarization."""

    summary: str
    sources: list[NoteSource] = field(default_factory=list)
    individual_summaries: list[NoteSummary] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class SummarizeTarget:
    """Resolved target for summarization."""

    target_type: Literal["single_note", "notebook", "tag_filter", "date_range"]
    notes: list[NoteSource]
    description: str  # Human-readable description


# ============================================================================
# Prompt Templates
# ============================================================================

SUMMARIZE_SYSTEM_PROMPT = """\
You are a helpful assistant summarizing personal notes.

Guidelines:
- Extract key points, decisions, and action items
- Preserve important dates, names, and specific details
- Organize information logically
- Use markdown formatting for readability
- Keep the summary concise but comprehensive
- If the note contains todos, highlight incomplete ones
"""

TLDR_SYSTEM_PROMPT = """\
You are a helpful assistant providing ultra-brief note summaries.

Guidelines:
- Provide 1-2 sentences maximum
- Focus on the single most important point or theme
- Skip all formatting and lists
- Be direct and concise
"""

MAP_PROMPT_TEMPLATE = """\
Summarize this note concisely:

---
Title: {title}
Date: {date}
Notebook: {notebook}
---

{content}
"""

REDUCE_PROMPT_TEMPLATE = """\
Synthesize these summaries from {note_count} notes into a single cohesive summary.

Target: {target_description}
Date range: {date_range}

Individual summaries:

{summaries}

Provide a unified summary that captures the main themes, key decisions, and important items across all notes.
"""

TLDR_REDUCE_PROMPT_TEMPLATE = """\
These are summaries from {note_count} notes. Provide a 1-2 sentence overview capturing the key theme.

{summaries}
"""


# ============================================================================
# Target Resolution
# ============================================================================


def resolve_target(
    target: str | None = None,
    notebook: str | None = None,
    tag: str | None = None,
    days: int | None = None,
    notes_root: Path | None = None,
) -> SummarizeTarget:
    """Resolve summarization target to a list of notes.

    Target identification logic:
    - No args -> today's daily note
    - "yesterday" or other fuzzy date -> that day's daily note
    - Contains "/" -> specific note path
    - No "/" -> notebook name -> all notes in that notebook
    - --tag -> filter notes by tag
    - --days N -> limit to last N days

    Args:
        target: Target string (optional)
        notebook: Notebook filter (--notebook)
        tag: Tag filter (--tag)
        days: Days filter (--days)
        notes_root: Override notes root

    Returns:
        SummarizeTarget with resolved notes

    Raises:
        ValueError: If target cannot be resolved or no notes found
    """
    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root

    # Calculate date range if days specified
    if days:
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
    else:
        start_date = None
        end_date = None

    # Priority 1: Tag filter (can combine with notebook)
    if tag:
        notes = _get_notes_by_tag(tag, notebook, start_date, end_date, notes_root)
        description = f"notes tagged #{tag}"
        if notebook:
            description += f" in {notebook}"
        if days:
            description += f" (last {days} days)"
        return SummarizeTarget(
            target_type="tag_filter",
            notes=notes,
            description=description,
        )

    # Priority 2: Specific target provided
    if target:
        # Try parsing as fuzzy date first (today, yesterday, etc.)
        parsed_date = parse_fuzzy_date(target)
        if parsed_date:
            note_path = get_daily_note_path(parsed_date, notes_root)
            if not note_path.exists():
                raise ValueError(f"No daily note exists for {parsed_date.isoformat()}")
            notes = [_load_note_source(note_path, notes_root)]
            description = (
                f"{target}'s note"
                if target in ("today", "yesterday")
                else f"note for {parsed_date.isoformat()}"
            )
            return SummarizeTarget(
                target_type="single_note",
                notes=notes,
                description=description,
            )

        # Check if it's a path (contains /)
        if "/" in target or "\\" in target:
            # Specific note path
            note_path = Path(target)
            if not note_path.suffix:
                note_path = note_path.with_suffix(".md")
            if not note_path.is_absolute():
                note_path = notes_root / note_path
            if not note_path.exists():
                raise ValueError(f"Note not found: {target}")
            notes = [_load_note_source(note_path, notes_root)]
            return SummarizeTarget(
                target_type="single_note",
                notes=notes,
                description=f"note {target}",
            )

        # Otherwise treat as notebook name
        notebook = target

    # Priority 3: Notebook specified (via --notebook or as target)
    if notebook:
        notes = _get_notebook_notes(notebook, start_date, end_date, notes_root)
        description = f"{notebook} notebook"
        if days:
            description += f" (last {days} days)"
        return SummarizeTarget(
            target_type="notebook",
            notes=notes,
            description=description,
        )

    # Priority 4: No target - default to today's daily note
    today = date.today()
    note_path = get_daily_note_path(today, notes_root)
    if not note_path.exists():
        raise ValueError("No daily note exists for today. Create one with 'nb today'.")
    notes = [_load_note_source(note_path, notes_root)]
    return SummarizeTarget(
        target_type="single_note",
        notes=notes,
        description="today's note",
    )


def _load_note_source(path: Path, notes_root: Path) -> NoteSource:
    """Load a note file into a NoteSource."""
    from nb.utils.markdown import (
        extract_date,
        extract_tags,
        extract_title,
        parse_note_file,
    )

    content = path.read_text(encoding="utf-8")
    meta, body = parse_note_file(path)

    # Determine relative path and notebook
    try:
        rel_path = path.relative_to(notes_root)
        notebook = rel_path.parts[0] if len(rel_path.parts) > 1 else None
    except ValueError:
        rel_path = path
        notebook = None

    return NoteSource(
        path=rel_path,
        title=extract_title(meta, body, path),
        content=content,
        date=extract_date(meta, path),
        notebook=notebook,
        tags=extract_tags(meta, body),
    )


def _get_notebook_notes(
    notebook: str,
    start_date: date | None,
    end_date: date | None,
    notes_root: Path,
) -> list[NoteSource]:
    """Get all notes from a notebook within optional date range."""
    if start_date or end_date:
        paths = list_notebook_notes_by_date(notebook, start_date, end_date, notes_root)
    else:
        paths = [notes_root / p for p in list_notes(notebook, notes_root)]

    if not paths:
        raise ValueError(f"No notes found in notebook '{notebook}'")

    return [_load_note_source(p, notes_root) for p in paths]


def _get_notes_by_tag(
    tag: str,
    notebook: str | None,
    start_date: date | None,
    end_date: date | None,
    notes_root: Path,
) -> list[NoteSource]:
    """Get notes with a specific tag."""
    from nb.index.db import get_db

    db = get_db()

    # Build query
    query = """
        SELECT DISTINCT n.path FROM notes n
        JOIN note_tags nt ON n.path = nt.note_path
        WHERE nt.tag = ?
    """
    params: list = [tag]

    if notebook:
        query += " AND n.notebook = ?"
        params.append(notebook)

    if start_date:
        query += " AND n.date >= ?"
        params.append(start_date.isoformat())

    if end_date:
        query += " AND n.date <= ?"
        params.append(end_date.isoformat())

    query += " ORDER BY n.date DESC"

    rows = db.fetchall(query, tuple(params))

    if not rows:
        raise ValueError(f"No notes found with tag '{tag}'")

    return [_load_note_source(notes_root / row["path"], notes_root) for row in rows]


# ============================================================================
# Single Note Summarization
# ============================================================================


def summarize_note(
    note: NoteSource,
    mode: Literal["summarize", "tldr"] = "summarize",
    custom_prompt: str | None = None,
    use_smart_model: bool = True,
) -> NoteSummary:
    """Summarize a single note (non-streaming).

    Args:
        note: The note to summarize
        mode: "summarize" for full summary, "tldr" for 1-2 sentences
        custom_prompt: Optional custom instructions
        use_smart_model: Use smart (better) or fast (cheaper) model

    Returns:
        NoteSummary with the generated summary
    """
    system = TLDR_SYSTEM_PROMPT if mode == "tldr" else SUMMARIZE_SYSTEM_PROMPT
    prompt = _build_single_note_prompt(note, custom_prompt)

    client = get_llm_client()
    response = client.complete(
        messages=[Message(role="user", content=prompt)],
        system=system,
        use_smart_model=use_smart_model,
    )

    return NoteSummary(
        path=note.path,
        title=note.title,
        summary=response.content,
        notebook=note.notebook,
    )


def summarize_note_stream(
    note: NoteSource,
    mode: Literal["summarize", "tldr"] = "summarize",
    custom_prompt: str | None = None,
    use_smart_model: bool = True,
) -> Iterator[StreamChunk]:
    """Stream summarization of a single note.

    Args:
        note: The note to summarize
        mode: "summarize" for full summary, "tldr" for 1-2 sentences
        custom_prompt: Optional custom instructions
        use_smart_model: Use smart (better) or fast (cheaper) model

    Yields:
        StreamChunk objects with content and token info
    """
    system = TLDR_SYSTEM_PROMPT if mode == "tldr" else SUMMARIZE_SYSTEM_PROMPT
    prompt = _build_single_note_prompt(note, custom_prompt)

    client = get_llm_client()
    yield from client.complete_stream(
        messages=[Message(role="user", content=prompt)],
        system=system,
        use_smart_model=use_smart_model,
    )


def _build_single_note_prompt(
    note: NoteSource, custom_prompt: str | None = None
) -> str:
    """Build prompt for single note summarization."""
    prompt = MAP_PROMPT_TEMPLATE.format(
        title=note.title or note.path.stem,
        date=note.date.isoformat() if note.date else "unknown",
        notebook=note.notebook or "unknown",
        content=note.content,
    )

    if custom_prompt:
        prompt += f"\n\nAdditional instructions: {custom_prompt}"

    return prompt


# ============================================================================
# Multi-Note Map-Reduce Summarization
# ============================================================================


def summarize_notes_map_reduce(
    target: SummarizeTarget,
    mode: Literal["summarize", "tldr"] = "summarize",
    custom_prompt: str | None = None,
    use_smart_model: bool = True,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> SummarizeResult:
    """Summarize multiple notes using map-reduce approach.

    Map phase: Summarize each note individually
    Reduce phase: Synthesize all summaries into a final summary

    Args:
        target: Resolved target with notes to summarize
        mode: "summarize" or "tldr"
        custom_prompt: Optional custom instructions
        use_smart_model: Model selection
        progress_callback: Optional callback(current, total, note_title) for progress

    Returns:
        SummarizeResult with final summary and individual summaries
    """
    individual_summaries: list[NoteSummary] = []
    total_input_tokens = 0
    total_output_tokens = 0

    # MAP PHASE: Summarize each note
    for i, note in enumerate(target.notes):
        if progress_callback:
            progress_callback(i + 1, len(target.notes), note.title or str(note.path))

        # Check if note already has summary in frontmatter (cache)
        existing_summary = _get_frontmatter_summary(note.path)
        if existing_summary and not custom_prompt:
            individual_summaries.append(
                NoteSummary(
                    path=note.path,
                    title=note.title,
                    summary=existing_summary,
                    notebook=note.notebook,
                )
            )
            continue

        # Generate new summary
        system = TLDR_SYSTEM_PROMPT if mode == "tldr" else SUMMARIZE_SYSTEM_PROMPT
        prompt = _build_single_note_prompt(note, custom_prompt)

        client = get_llm_client()
        response = client.complete(
            messages=[Message(role="user", content=prompt)],
            system=system,
            use_smart_model=use_smart_model,
        )

        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens

        individual_summaries.append(
            NoteSummary(
                path=note.path,
                title=note.title,
                summary=response.content,
                notebook=note.notebook,
            )
        )

    # REDUCE PHASE: Synthesize all summaries
    final_summary, reduce_input, reduce_output = _reduce_summaries(
        individual_summaries,
        target.description,
        target.notes,
        mode=mode,
        custom_prompt=custom_prompt,
        use_smart_model=use_smart_model,
    )

    total_input_tokens += reduce_input
    total_output_tokens += reduce_output

    return SummarizeResult(
        summary=final_summary,
        sources=target.notes,
        individual_summaries=individual_summaries,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )


def _reduce_summaries(
    summaries: list[NoteSummary],
    target_description: str,
    notes: list[NoteSource],
    mode: Literal["summarize", "tldr"],
    custom_prompt: str | None,
    use_smart_model: bool,
) -> tuple[str, int, int]:
    """Synthesize individual summaries into final summary.

    Returns:
        Tuple of (summary_text, input_tokens, output_tokens)
    """
    # Format individual summaries
    formatted_summaries = []
    for i, s in enumerate(summaries, 1):
        formatted_summaries.append(f"[{i}] {s.title or s.path}\n{s.summary}")

    summaries_text = "\n\n---\n\n".join(formatted_summaries)

    # Calculate date range
    dates = [n.date for n in notes if n.date]
    if dates:
        date_range = f"{min(dates).isoformat()} to {max(dates).isoformat()}"
    else:
        date_range = "unknown"

    # Build reduce prompt
    if mode == "tldr":
        prompt = TLDR_REDUCE_PROMPT_TEMPLATE.format(
            note_count=len(summaries),
            summaries=summaries_text,
        )
    else:
        prompt = REDUCE_PROMPT_TEMPLATE.format(
            note_count=len(summaries),
            target_description=target_description,
            date_range=date_range,
            summaries=summaries_text,
        )

    if custom_prompt:
        prompt += f"\n\nAdditional instructions: {custom_prompt}"

    system = TLDR_SYSTEM_PROMPT if mode == "tldr" else SUMMARIZE_SYSTEM_PROMPT

    client = get_llm_client()
    response = client.complete(
        messages=[Message(role="user", content=prompt)],
        system=system,
        use_smart_model=use_smart_model,
    )

    return response.content, response.input_tokens, response.output_tokens


def _get_frontmatter_summary(note_path: Path) -> str | None:
    """Get existing summary from note frontmatter if present."""
    config = get_config()

    if not note_path.is_absolute():
        note_path = config.notes_root / note_path

    if not note_path.exists():
        return None

    try:
        with note_path.open(encoding="utf-8") as f:
            post = frontmatter.load(f)
        return post.metadata.get("summary")
    except Exception:
        return None


# ============================================================================
# Frontmatter Update
# ============================================================================


def update_note_frontmatter_summary(
    note_path: Path,
    summary: str,
    notes_root: Path | None = None,
) -> None:
    """Update a note's frontmatter with a summary.

    Adds or updates the 'summary' key in YAML frontmatter.

    Args:
        note_path: Path to the note (relative or absolute)
        summary: Summary text to store
        notes_root: Override notes root
    """
    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root

    # Resolve path
    if not note_path.is_absolute():
        note_path = notes_root / note_path

    if not note_path.exists():
        raise ValueError(f"Note not found: {note_path}")

    # Load existing content
    with note_path.open(encoding="utf-8") as f:
        post = frontmatter.load(f)

    # Update/add summary key
    post.metadata["summary"] = summary

    # Write back
    with note_path.open("w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))


# ============================================================================
# Raw Content TLDR (for inbox clipping)
# ============================================================================

INBOX_TLDR_SYSTEM_PROMPT = """\
You are a helpful assistant providing ultra-brief summaries of web articles.

Guidelines:
- Provide 1-2 sentences maximum
- Focus on the core topic and key takeaway
- Be direct and informative
- Skip all formatting
"""


def generate_content_tldr(
    content: str,
    title: str | None = None,
    use_smart_model: bool = False,
) -> str | None:
    """Generate a TLDR summary for raw content.

    This is a simplified interface for inbox clipping that handles
    errors gracefully and returns None on failure.

    Args:
        content: The markdown content to summarize
        title: Optional title for context
        use_smart_model: Use smart (better) or fast (cheaper) model

    Returns:
        TLDR string, or None if generation failed
    """
    from nb.core.llm import LLMConfigError, LLMError, Message, get_llm_client

    # Truncate very long content to avoid token limits
    max_content_length = 15000
    if len(content) > max_content_length:
        content = content[:max_content_length] + "\n\n[... truncated ...]"

    prompt = "Summarize this article in 1-2 sentences:\n\n"
    if title:
        prompt += f"Title: {title}\n\n"
    prompt += content

    try:
        client = get_llm_client()
        response = client.complete(
            messages=[Message(role="user", content=prompt)],
            system=INBOX_TLDR_SYSTEM_PROMPT,
            use_smart_model=use_smart_model,
        )
        return response.content.strip()
    except (LLMConfigError, LLMError):
        # Graceful failure - return None to indicate no summary available
        return None
    except Exception:
        # Catch any other unexpected errors
        return None


# ============================================================================
# Save to Note
# ============================================================================


def append_summary_to_note(
    summary: str,
    target_description: str,
    note_path: Path | str | None = None,
    section_title: str | None = None,
    notes_root: Path | None = None,
) -> Path:
    """Append summary to a note file.

    Args:
        summary: The summary text
        target_description: What was summarized (for the section header)
        note_path: Target note path, or None for today's note
        section_title: Optional custom section heading
        notes_root: Override notes root

    Returns:
        Path to the note that was modified
    """
    config = get_config()
    if notes_root is None:
        notes_root = config.notes_root

    # Resolve target note
    if note_path is None or note_path == "today":
        note_path = ensure_daily_note(date.today(), notes_root)
    else:
        if isinstance(note_path, str):
            note_path = Path(note_path)
        if not note_path.suffix:
            note_path = note_path.with_suffix(".md")
        if not note_path.is_absolute():
            note_path = notes_root / note_path

        if not note_path.exists():
            # Create the note
            note_path.parent.mkdir(parents=True, exist_ok=True)
            note_path.write_text(f"# {note_path.stem}\n\n", encoding="utf-8")

    # Read current content
    content = note_path.read_text(encoding="utf-8")

    # Build section header
    if section_title is None:
        section_title = f"## Summary: {target_description}"

    # Append summary
    if not content.endswith("\n"):
        content += "\n"
    content += f"\n{section_title}\n\n{summary}\n"

    # Write back
    note_path.write_text(content, encoding="utf-8")

    return note_path
