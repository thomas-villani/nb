"""RAG-based question answering over notes.

Uses localvectordb's advanced search features (enriched return type, QueryBuilder)
to retrieve relevant context, then uses the LLM to generate answers with citations.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nb.config import get_config
from nb.core.llm import Message, StreamChunk, get_llm_client
from nb.index.search import SearchResult, get_search

if TYPE_CHECKING:
    pass

# Approximate tokens per character (conservative estimate)
# Claude uses ~4 chars/token for English, but we use 3 to be safe
CHARS_PER_TOKEN = 3

# Model context limits (input tokens)
# These are conservative limits leaving room for the response
MODEL_CONTEXT_LIMITS = {
    # Anthropic models (new short names and legacy full names)
    "claude-sonnet-4-5": 180000,  # 200k context, leave room for output
    "claude-haiku-4-5": 180000,
    "claude-sonnet-4-20250514": 180000,  # Legacy names
    "claude-haiku-3-5-20241022": 180000,
    "claude-3-5-sonnet": 180000,
    "claude-3-haiku": 180000,
    # OpenAI models - MUST UPDATE WITH GPT5
    "gpt-4o": 120000,
    "gpt-4o-mini": 120000,
    "gpt-4-turbo": 120000,
    "gpt-4": 7000,
    "gpt-3.5-turbo": 15000,
}

# Default context limit if model not recognized
DEFAULT_CONTEXT_LIMIT = 30000


def _estimate_tokens(text: str) -> int:
    """Estimate token count from text length.

    Uses a conservative chars-per-token ratio.
    """
    return len(text) // CHARS_PER_TOKEN


def _get_model_context_limit(model: str) -> int:
    """Get the context token limit for a model."""
    # Check exact match first
    if model in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model]

    # Check partial matches
    model_lower = model.lower()
    for key, limit in MODEL_CONTEXT_LIMITS.items():
        if key in model_lower or model_lower in key:
            return limit

    return DEFAULT_CONTEXT_LIMIT


@dataclass
class NoteReference:
    """Reference to a note used as context."""

    path: str
    title: str | None
    snippet: str
    score: float
    notebook: str | None = None


@dataclass
class AnswerResult:
    """Result from a question-answering query."""

    answer: str
    sources: list[NoteReference] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


# Default system prompt for question answering
DEFAULT_ASK_SYSTEM_PROMPT = """\
You are a helpful assistant answering questions based on the user's personal notes.
Your task is to answer the user's question using ONLY the information provided in the context.

Guidelines:
- Answer directly and concisely based on the context provided
- If the context doesn't contain relevant information, say so clearly
- When citing information, reference the source note path in parentheses
- Do not make up information not present in the context
- If multiple notes discuss the topic, synthesize the information
- Use markdown formatting for readability when appropriate
"""


@dataclass
class RetrievedContext:
    """Context retrieved from notes for RAG."""

    path: str
    title: str | None
    content: str
    score: float
    notebook: str | None = None
    date: str | None = None
    chunk_count: int = 1  # Number of chunks combined (for enriched results)


def _retrieve_context_enriched(
    question: str,
    notebook: str | None = None,
    tag: str | None = None,
    max_results: int = 5,
    context_window: int = 3,
) -> list[RetrievedContext]:
    """Retrieve context using enriched return type for better RAG.

    Uses localvectordb's enriched return type which combines matching chunks
    with semantically similar chunks from the same document.

    Args:
        question: The question to find context for.
        notebook: Filter to specific notebook.
        tag: Filter to notes with specific tag.
        max_results: Maximum number of document results.
        context_window: Number of similar chunks to include per match.

    Returns:
        List of RetrievedContext objects with enriched content.
    """
    search = get_search()
    config = get_config()

    # Build filters using MongoDB-style operators
    filters: dict[str, Any] = {}
    if notebook:
        filters["notebook"] = notebook
    if tag:
        filters["tags"] = {"$contains": tag}

    try:
        # Use enriched return type for better context in RAG
        # This combines matching chunks with semantically similar chunks
        results = search.db.query(
            question,
            search_type="hybrid",
            k=max_results,
            filters=filters if filters else None,
            vector_weight=config.search.vector_weight,
            score_threshold=config.search.score_threshold,
            return_type="enriched",
            context_window=context_window,
        )
    except Exception as e:
        # Fall back to standard search if enriched not available
        error_msg = str(e).lower()
        if "enriched" in error_msg or "return_type" in error_msg:
            # Fall back to chunks
            results = search.db.query(
                question,
                search_type="hybrid",
                k=max_results * 2,  # Get more chunks to compensate
                filters=filters if filters else None,
                vector_weight=config.search.vector_weight,
                score_threshold=config.search.score_threshold,
                return_type="chunks",
            )
        else:
            raise

    contexts = []
    for r in results:
        metadata = r.metadata or {}
        # Check for enriched metadata
        chunk_count = 1
        if "_matched_chunk_indices" in metadata:
            chunk_count = len(metadata.get("_all_chunk_indices", [1]))

        contexts.append(
            RetrievedContext(
                path=metadata.get("path", ""),
                title=metadata.get("title"),
                content=r.content or "",
                score=r.score,
                notebook=metadata.get("notebook"),
                date=metadata.get("date"),
                chunk_count=chunk_count,
            )
        )

    return contexts


def _truncate_contexts_to_limit(
    contexts: list[RetrievedContext],
    max_tokens: int,
    question: str,
    system_prompt: str,
) -> list[RetrievedContext]:
    """Truncate contexts to fit within token limit.

    Prioritizes higher-scored contexts. Will truncate individual contexts
    if needed to fit more sources.

    Args:
        contexts: List of contexts sorted by relevance.
        max_tokens: Maximum tokens for the entire prompt.
        question: The question (to account for in budget).
        system_prompt: The system prompt (to account for in budget).

    Returns:
        Truncated list of contexts that fit within the limit.
    """
    # Reserve tokens for system prompt, question, and formatting
    reserved_tokens = (
        _estimate_tokens(system_prompt)
        + _estimate_tokens(question)
        + 500  # Buffer for prompt template and formatting
    )

    available_tokens = max_tokens - reserved_tokens
    if available_tokens <= 0:
        return []

    result = []
    used_tokens = 0

    for ctx in contexts:
        ctx_tokens = _estimate_tokens(ctx.content) + 100  # Header overhead

        if used_tokens + ctx_tokens <= available_tokens:
            # Fits entirely
            result.append(ctx)
            used_tokens += ctx_tokens
        elif used_tokens < available_tokens * 0.9:
            # Truncate this context to fit remaining space
            remaining_tokens = available_tokens - used_tokens - 100
            if remaining_tokens > 200:  # Only include if meaningful amount
                max_chars = remaining_tokens * CHARS_PER_TOKEN
                truncated_content = ctx.content[:max_chars]
                if len(truncated_content) < len(ctx.content):
                    truncated_content += "\n[... content truncated ...]"

                result.append(
                    RetrievedContext(
                        path=ctx.path,
                        title=ctx.title,
                        content=truncated_content,
                        score=ctx.score,
                        notebook=ctx.notebook,
                        date=ctx.date,
                        chunk_count=ctx.chunk_count,
                    )
                )
                used_tokens = available_tokens  # Mark as full
        else:
            # No more room
            break

    return result


def _build_context_prompt(
    question: str,
    contexts: list[RetrievedContext],
    max_tokens: int | None = None,
    system_prompt: str | None = None,
) -> tuple[str, list[RetrievedContext]]:
    """Build the prompt with retrieved context, respecting token limits.

    Args:
        question: The user's question.
        contexts: Retrieved contexts to include.
        max_tokens: Maximum tokens for context (None = no limit).
        system_prompt: System prompt to account for in budget.

    Returns:
        Tuple of (formatted prompt string, contexts actually used).
    """
    # Truncate contexts if needed
    if max_tokens and system_prompt:
        contexts = _truncate_contexts_to_limit(
            contexts, max_tokens, question, system_prompt
        )

    context_parts = []

    for i, ctx in enumerate(contexts, 1):
        title = ctx.title or Path(ctx.path).stem
        header = f"[{i}] {ctx.path}"
        if ctx.notebook:
            header += f" (notebook: {ctx.notebook})"
        if ctx.date:
            header += f" (date: {ctx.date})"

        context_parts.append(f"---\n{header}\nTitle: {title}\n\n{ctx.content}\n")

    context = "\n".join(context_parts)

    prompt = f"""Based on the following notes from my personal notebook:

{context}

Question: {question}

Please answer the question based on the context above. If citing specific information, reference the note path."""

    return prompt, contexts


def _contexts_to_references(contexts: list[RetrievedContext]) -> list[NoteReference]:
    """Convert retrieved contexts to note references for display."""
    return [
        NoteReference(
            path=ctx.path,
            title=ctx.title,
            snippet=(
                ctx.content[:200] + "..." if len(ctx.content) > 200 else ctx.content
            ),
            score=ctx.score,
            notebook=ctx.notebook,
        )
        for ctx in contexts
    ]


def _search_results_to_references(results: list[SearchResult]) -> list[NoteReference]:
    """Convert search results to note references."""
    return [
        NoteReference(
            path=r.path,
            title=r.title,
            snippet=r.snippet[:200] + "..." if len(r.snippet) > 200 else r.snippet,
            score=r.score,
            notebook=r.notebook,
        )
        for r in results
    ]


def ask_notes(
    question: str,
    notebook: str | None = None,
    note_path: str | None = None,
    tag: str | None = None,
    max_context_results: int = 5,
    context_window: int = 3,
    use_smart_model: bool = True,
    system_prompt: str | None = None,
    max_context_tokens: int | None = None,
) -> AnswerResult:
    """Answer a question using RAG over notes.

    Uses localvectordb's enriched return type which retrieves matching chunks
    along with semantically similar chunks from the same document for better context.

    Args:
        question: The question to answer.
        notebook: Filter to a specific notebook.
        note_path: Filter to a specific note path (reads entire note).
        tag: Filter to notes with a specific tag.
        max_context_results: Maximum number of enriched results (documents).
        context_window: Number of similar chunks to include per match.
        use_smart_model: If True, use smart model for better answers.
        system_prompt: Custom system prompt (overrides default).
        max_context_tokens: Maximum tokens for context. If None, uses model limit.

    Returns:
        AnswerResult with the answer and source references.

    Raises:
        LLMError: If the LLM request fails.
        ValueError: If no relevant context is found.
    """
    config = get_config()
    system = system_prompt or DEFAULT_ASK_SYSTEM_PROMPT

    # Determine the model to use for context limit calculation
    model = config.llm.models.smart if use_smart_model else config.llm.models.fast

    # Get context limit based on model if not specified
    if max_context_tokens is None:
        max_context_tokens = _get_model_context_limit(model)

    # If a specific note is provided, read it directly instead of searching
    if note_path:
        path = Path(note_path)
        if not path.is_absolute():
            path = config.notes_root / path

        if path.exists():
            content = path.read_text(encoding="utf-8")
            contexts = [
                RetrievedContext(
                    path=note_path,
                    title=path.stem,
                    content=content,
                    score=1.0,
                    notebook=notebook,
                )
            ]
        else:
            raise ValueError(f"Note not found: {note_path}")
    else:
        # Use enriched retrieval for better RAG context
        contexts = _retrieve_context_enriched(
            question=question,
            notebook=notebook,
            tag=tag,
            max_results=max_context_results,
            context_window=context_window,
        )

        if not contexts:
            return AnswerResult(
                answer="I couldn't find any relevant notes to answer your question. "
                "Try rephrasing or broadening your search.",
                sources=[],
            )

    # Build the prompt with context, respecting token limits
    prompt, used_contexts = _build_context_prompt(
        question, contexts, max_context_tokens, system
    )

    # Get the LLM client and generate answer
    client = get_llm_client()

    response = client.complete(
        messages=[Message(role="user", content=prompt)],
        system=system,
        use_smart_model=use_smart_model,
    )

    return AnswerResult(
        answer=response.content,
        sources=_contexts_to_references(used_contexts),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )


def ask_notes_stream(
    question: str,
    notebook: str | None = None,
    note_path: str | None = None,
    tag: str | None = None,
    max_context_results: int = 5,
    context_window: int = 3,
    use_smart_model: bool = True,
    system_prompt: str | None = None,
    max_context_tokens: int | None = None,
) -> tuple[list[NoteReference], Iterator[StreamChunk]]:
    """Stream an answer to a question using RAG over notes.

    Same as ask_notes but returns a streaming iterator for the answer.

    Args:
        question: The question to answer.
        notebook: Filter to a specific notebook.
        note_path: Filter to a specific note path (reads entire note).
        tag: Filter to notes with a specific tag.
        max_context_results: Maximum number of enriched results (documents).
        context_window: Number of similar chunks to include per match.
        use_smart_model: If True, use smart model for better answers.
        system_prompt: Custom system prompt (overrides default).
        max_context_tokens: Maximum tokens for context. If None, uses model limit.

    Returns:
        Tuple of (source references, stream iterator).

    Raises:
        LLMError: If the LLM request fails.
        ValueError: If no relevant context is found.
    """
    config = get_config()
    system = system_prompt or DEFAULT_ASK_SYSTEM_PROMPT

    # Determine the model to use for context limit calculation
    model = config.llm.models.smart if use_smart_model else config.llm.models.fast

    # Get context limit based on model if not specified
    if max_context_tokens is None:
        max_context_tokens = _get_model_context_limit(model)

    # If a specific note is provided, read it directly instead of searching
    if note_path:
        path = Path(note_path)
        if not path.is_absolute():
            path = config.notes_root / path

        if path.exists():
            content = path.read_text(encoding="utf-8")
            contexts = [
                RetrievedContext(
                    path=note_path,
                    title=path.stem,
                    content=content,
                    score=1.0,
                    notebook=notebook,
                )
            ]
        else:
            raise ValueError(f"Note not found: {note_path}")
    else:
        # Use enriched retrieval for better RAG context
        contexts = _retrieve_context_enriched(
            question=question,
            notebook=notebook,
            tag=tag,
            max_results=max_context_results,
            context_window=context_window,
        )

        if not contexts:
            raise ValueError(
                "No relevant notes found. Try rephrasing or broadening your search."
            )

    # Build the prompt with context, respecting token limits
    prompt, used_contexts = _build_context_prompt(
        question, contexts, max_context_tokens, system
    )
    sources = _contexts_to_references(used_contexts)

    # Get the LLM client and start streaming
    client = get_llm_client()

    stream = client.complete_stream(
        messages=[Message(role="user", content=prompt)],
        system=system,
        use_smart_model=use_smart_model,
    )

    return sources, stream
