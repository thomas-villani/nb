"""AI-powered research agent.

Uses LLM tool-calling to perform web research and generate reports.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from nb.config import get_config
from nb.core.clip import fetch_url, html_to_markdown
from nb.core.llm import (
    Message,
    ToolCall,
    ToolDefinition,
    ToolResult,
    get_llm_client,
)
from nb.core.notes import ensure_daily_note
from nb.core.search import (
    SearchAPIError,
    SearchResult,
    format_results_as_markdown,
    search_news,
    search_patents,
    search_scholar,
    search_web,
)

# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ResearchSource:
    """A source found during research."""

    url: str
    title: str
    snippet: str
    content: str | None = None  # Full content if fetched
    search_type: str = "web"
    fetched: bool = False


@dataclass
class ResearchResult:
    """Result of a research session."""

    query: str
    report: str
    sources: list[ResearchSource]
    input_tokens: int
    output_tokens: int


@dataclass
class ResearchContext:
    """Context for the research agent loop."""

    sources: list[ResearchSource] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    vector_db: Any = None  # VectorDB instance when use_vectordb=True
    vector_collection: str = "research_temp"


# ============================================================================
# System Prompts
# ============================================================================

RESEARCH_SYSTEM_PROMPT = """You are a research assistant. Your task is to gather comprehensive information about the given topic using the available search and fetch tools.

Strategy: {strategy}

Available tools:
{available_tools}

Guidelines:
1. Start with broad searches to understand the topic landscape
2. Use fetch_url to get detailed content from the most promising sources
3. Cross-reference information from multiple authoritative sources
4. For depth strategy: follow leads and do follow-up searches based on findings
5. For breadth strategy: search multiple queries first, then selectively fetch
6. For auto strategy: adapt based on query complexity and findings
7. Focus on recent, authoritative sources when available
8. Track which sources you've already searched/fetched to avoid duplicates

When you have gathered sufficient information, call complete_research with a well-structured markdown report.

Report format:
- **Executive Summary**: 2-3 sentences summarizing key findings
- **Key Findings**: Bullet points of the most important facts
- **Detailed Analysis**: Sections covering different aspects of the topic
- **Sources**: Cite sources inline using [Source Title](url) format

Token Budget: You have approximately {token_budget:,} tokens. Current usage: {tokens_used:,}. Plan accordingly.
"""

BUDGET_WARNING_PROMPT = """
IMPORTANT: You are approaching your token budget limit ({tokens_used:,}/{token_budget:,} tokens used).
Please wrap up your research and call complete_research with your findings now.
"""


# ============================================================================
# Tool Definitions
# ============================================================================


def get_research_tools(
    use_vectordb: bool = False,
    search_types: list[str] | None = None,
) -> list[ToolDefinition]:
    """Get tool definitions for the research agent.

    Args:
        use_vectordb: Whether to include vector DB query tool
        search_types: Restrict to specific search types

    Returns:
        List of tool definitions
    """
    allowed_types = search_types or ["web", "news", "scholar", "patents"]

    tools = []

    if "web" in allowed_types:
        tools.append(
            ToolDefinition(
                name="web_search",
                description="Search the web for information on a topic. Returns titles, URLs, and snippets.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results (default 10, max 20)",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            )
        )

    if "news" in allowed_types:
        tools.append(
            ToolDefinition(
                name="news_search",
                description="Search news articles. Good for recent events and developments.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results (default 10)",
                            "default": 10,
                        },
                        "since": {
                            "type": "string",
                            "enum": ["hour", "day", "week", "month", "year"],
                            "description": "Time filter (default: week)",
                            "default": "week",
                        },
                    },
                    "required": ["query"],
                },
            )
        )

    if "scholar" in allowed_types:
        tools.append(
            ToolDefinition(
                name="scholar_search",
                description="Search academic papers and research. Good for scientific topics.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results (default 10)",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            )
        )

    if "patents" in allowed_types:
        tools.append(
            ToolDefinition(
                name="patents_search",
                description="Search patents. Good for inventions and technical innovations.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results (default 10)",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            )
        )

    # Fetch URL tool
    tools.append(
        ToolDefinition(
            name="fetch_url",
            description="Fetch and extract the main content from a URL. Use this to get detailed information from promising search results.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    },
                },
                "required": ["url"],
            },
        )
    )

    # Vector DB query tool (optional)
    if use_vectordb:
        tools.append(
            ToolDefinition(
                name="query_collected",
                description="Query the content you've already collected using semantic search. Use this to find specific information across fetched sources.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The semantic query",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results (default 5)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            )
        )

    # Complete research tool
    tools.append(
        ToolDefinition(
            name="complete_research",
            description="Call this when you have gathered sufficient information and are ready to provide the final research report.",
            parameters={
                "type": "object",
                "properties": {
                    "report": {
                        "type": "string",
                        "description": "The complete research report in markdown format",
                    },
                },
                "required": ["report"],
            },
        )
    )

    return tools


# ============================================================================
# Tool Execution
# ============================================================================


def _execute_web_search(args: dict[str, Any], context: ResearchContext) -> str:
    """Execute web search tool."""
    query = args.get("query", "")
    num_results = min(args.get("num_results", 10), 20)

    try:
        results = search_web(query, num_results)
        _add_sources_from_results(results, "web", context)
        return format_results_as_markdown(results, "web")
    except SearchAPIError as e:
        return f"Search failed: {e}"


def _execute_news_search(args: dict[str, Any], context: ResearchContext) -> str:
    """Execute news search tool."""
    query = args.get("query", "")
    num_results = min(args.get("num_results", 10), 20)
    since = args.get("since", "week")

    try:
        results = search_news(query, num_results, since)
        _add_sources_from_results(results, "news", context)
        return format_results_as_markdown(results, "news")
    except SearchAPIError as e:
        return f"News search failed: {e}"


def _execute_scholar_search(args: dict[str, Any], context: ResearchContext) -> str:
    """Execute scholar search tool."""
    query = args.get("query", "")
    num_results = min(args.get("num_results", 10), 20)

    try:
        results = search_scholar(query, num_results)
        _add_sources_from_results(results, "scholar", context)
        return format_results_as_markdown(results, "scholar")
    except SearchAPIError as e:
        return f"Scholar search failed: {e}"


def _execute_patents_search(args: dict[str, Any], context: ResearchContext) -> str:
    """Execute patents search tool."""
    query = args.get("query", "")
    num_results = min(args.get("num_results", 10), 20)

    try:
        results = search_patents(query, num_results)
        _add_sources_from_results(results, "patents", context)
        return format_results_as_markdown(results, "patents")
    except SearchAPIError as e:
        return f"Patents search failed: {e}"


def _execute_fetch_url(args: dict[str, Any], context: ResearchContext) -> str:
    """Execute fetch URL tool."""
    url = args.get("url", "")

    if not url:
        return "Error: No URL provided"

    try:
        html = fetch_url(url)
        markdown = html_to_markdown(html)

        # Truncate very long content
        max_chars = 15000
        if len(markdown) > max_chars:
            markdown = markdown[:max_chars] + "\n\n[Content truncated...]"

        # Update source if we have it
        for source in context.sources:
            if source.url == url:
                source.content = markdown
                source.fetched = True
                break
        else:
            # Add new source
            context.sources.append(
                ResearchSource(
                    url=url,
                    title=url,
                    snippet="",
                    content=markdown,
                    fetched=True,
                )
            )

        # Index in vector DB if enabled
        if context.vector_db is not None:
            _index_content_in_vectordb(url, markdown, context)

        return f"## Content from {url}\n\n{markdown}"
    except Exception as e:
        return f"Failed to fetch URL: {e}"


def _execute_query_collected(args: dict[str, Any], context: ResearchContext) -> str:
    """Execute vector DB query tool."""
    if context.vector_db is None:
        return "Error: Vector DB not enabled for this research session"

    query = args.get("query", "")
    num_results = args.get("num_results", 5)

    try:
        results = context.vector_db.query(
            query,
            k=num_results,
            return_type="chunks",
        )

        if not results:
            return "No matching content found in collected sources."

        output = ["## Relevant content from collected sources\n"]
        for i, result in enumerate(results, 1):
            url = (
                result.metadata.get("url", "unknown")
                if hasattr(result, "metadata")
                else "unknown"
            )
            content = (
                result.content[:2000]
                if hasattr(result, "content")
                else str(result)[:2000]
            )
            output.append(f"### Result {i} (from {url})\n{content}\n")

        return "\n".join(output)
    except Exception as e:
        return f"Vector query failed: {e}"


def execute_tool(tool_call: ToolCall, context: ResearchContext) -> ToolResult:
    """Execute a tool call and return the result.

    Args:
        tool_call: The tool call from the LLM
        context: Research context

    Returns:
        ToolResult with the output
    """
    name = tool_call.name
    args = tool_call.arguments

    try:
        if name == "web_search":
            result = _execute_web_search(args, context)
        elif name == "news_search":
            result = _execute_news_search(args, context)
        elif name == "scholar_search":
            result = _execute_scholar_search(args, context)
        elif name == "patents_search":
            result = _execute_patents_search(args, context)
        elif name == "fetch_url":
            result = _execute_fetch_url(args, context)
        elif name == "query_collected":
            result = _execute_query_collected(args, context)
        elif name == "complete_research":
            # This is handled specially in the main loop
            result = "Research complete."
        else:
            result = f"Unknown tool: {name}"
            return ToolResult(tool_call_id=tool_call.id, content=result, is_error=True)

        return ToolResult(tool_call_id=tool_call.id, content=result)
    except Exception as e:
        return ToolResult(
            tool_call_id=tool_call.id, content=f"Tool error: {e}", is_error=True
        )


# ============================================================================
# Helper Functions
# ============================================================================


def _add_sources_from_results(
    results: list[SearchResult],
    search_type: str,
    context: ResearchContext,
) -> None:
    """Add search results to the context sources."""
    existing_urls = {s.url for s in context.sources}

    for result in results:
        if result.url not in existing_urls:
            context.sources.append(
                ResearchSource(
                    url=result.url,
                    title=result.title,
                    snippet=result.snippet,
                    search_type=search_type,
                )
            )
            existing_urls.add(result.url)


def _index_content_in_vectordb(
    url: str,
    content: str,
    context: ResearchContext,
) -> None:
    """Index fetched content in the vector DB."""
    if context.vector_db is None:
        return

    try:
        # Use upsert to add content (will be chunked automatically)
        context.vector_db.upsert(
            documents=[content],
            metadata=[{"url": url}],
            ids=[url],
        )
    except Exception:
        pass  # Silently fail on indexing errors


def _init_vectordb(context: ResearchContext) -> None:
    """Initialize vector DB for the research session."""
    try:
        import tempfile

        from localvectordb import VectorDB

        config = get_config()

        # Create a temporary directory for the research vector DB
        temp_dir = tempfile.mkdtemp(prefix="nb_research_")

        # Build embedding config
        embedding_config = {}
        if config.embeddings.base_url:
            embedding_config["base_url"] = config.embeddings.base_url
        if config.embeddings.api_key:
            embedding_config["api_key"] = config.embeddings.api_key

        context.vector_db = VectorDB(
            name=context.vector_collection,
            base_path=temp_dir,
            embedding_provider=config.embeddings.provider,
            embedding_model=config.embeddings.model,
            embedding_config=embedding_config if embedding_config else None,
        )
        # Store temp dir for cleanup
        context.vector_collection = temp_dir
    except ImportError:
        context.vector_db = None
    except Exception:
        context.vector_db = None


def _cleanup_vectordb(context: ResearchContext) -> None:
    """Clean up the temporary vector DB."""
    if context.vector_db is not None:
        try:
            context.vector_db.close()
        except Exception:
            pass

        # Clean up temp directory
        try:
            import shutil

            if context.vector_collection.startswith(("C:\\", "/tmp", "/var")):
                shutil.rmtree(context.vector_collection, ignore_errors=True)
        except Exception:
            pass


def _format_available_tools(tools: list[ToolDefinition]) -> str:
    """Format tool list for system prompt."""
    lines = []
    for tool in tools:
        lines.append(f"- {tool.name}: {tool.description}")
    return "\n".join(lines)


# ============================================================================
# Main Research Function
# ============================================================================


def research(
    query: str,
    strategy: Literal["breadth", "depth", "auto"] = "auto",
    max_sources: int = 10,
    search_types: list[str] | None = None,
    use_smart_model: bool = True,
    use_vectordb: bool = False,
    token_budget: int = 100000,
    progress_callback: Callable[[str], None] | None = None,
) -> ResearchResult:
    """Perform AI-assisted research on a topic.

    Args:
        query: The research query/topic
        strategy: Research strategy (breadth, depth, or auto)
        max_sources: Maximum number of sources to include in final result
        search_types: Restrict to specific search types (web, news, scholar, patents)
        use_smart_model: Use smart model (True) or fast model (False)
        use_vectordb: Use vector DB for context management
        token_budget: Maximum tokens to consume
        progress_callback: Called with progress updates

    Returns:
        ResearchResult with the report and sources
    """
    context = ResearchContext()

    # Initialize vector DB if requested
    if use_vectordb:
        if progress_callback:
            progress_callback("Initializing vector database...")
        _init_vectordb(context)

    try:
        # Get tools
        tools = get_research_tools(
            use_vectordb=context.vector_db is not None,
            search_types=search_types,
        )

        # Build initial system prompt
        system_prompt = RESEARCH_SYSTEM_PROMPT.format(
            strategy=strategy,
            available_tools=_format_available_tools(tools),
            token_budget=token_budget,
            tokens_used=0,
        )

        # Initialize conversation
        context.messages = [
            Message(role="user", content=f"Research topic: {query}"),
        ]

        client = get_llm_client()
        report = ""

        # Agent loop
        while True:
            # Check token budget
            total_tokens = context.input_tokens + context.output_tokens
            if total_tokens >= token_budget * 0.9:
                # Approaching budget - add warning
                system_prompt += BUDGET_WARNING_PROMPT.format(
                    tokens_used=total_tokens,
                    token_budget=token_budget,
                )

            if total_tokens >= token_budget:
                # Over budget - force completion
                if progress_callback:
                    progress_callback("Token budget reached, completing research...")
                report = _generate_forced_report(
                    query, context, client, use_smart_model
                )
                break

            # Call LLM
            response = client.complete(
                messages=context.messages,
                system=system_prompt,
                tools=tools,
                use_smart_model=use_smart_model,
            )

            # Update token counts
            context.input_tokens += response.input_tokens
            context.output_tokens += response.output_tokens

            # Check for tool calls
            if response.tool_calls:
                # Add assistant message with tool calls
                context.messages.append(
                    Message(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )

                # Process each tool call
                for tool_call in response.tool_calls:
                    if progress_callback:
                        progress_callback(f"Calling {tool_call.name}...")

                    # Check for completion
                    if tool_call.name == "complete_research":
                        report = tool_call.arguments.get("report", "")
                        break

                    # Execute tool
                    result = execute_tool(tool_call, context)

                    # Add tool result message
                    context.messages.append(
                        Message(role="tool", content="", tool_result=result)
                    )

                # Check if research is complete
                if report:
                    break
            else:
                # No tool calls - LLM provided text response
                # This shouldn't happen often, but handle it
                context.messages.append(
                    Message(role="assistant", content=response.content)
                )

                # If LLM stopped without calling complete_research, prompt it
                if response.stop_reason == "end_turn":
                    context.messages.append(
                        Message(
                            role="user",
                            content="Please continue researching or call complete_research with your findings.",
                        )
                    )

    finally:
        # Cleanup vector DB
        if use_vectordb:
            _cleanup_vectordb(context)

    # Limit sources in result
    sources = context.sources[:max_sources]

    return ResearchResult(
        query=query,
        report=report,
        sources=sources,
        input_tokens=context.input_tokens,
        output_tokens=context.output_tokens,
    )


def _generate_forced_report(
    query: str,
    context: ResearchContext,
    client: Any,
    use_smart_model: bool,
) -> str:
    """Generate a report when token budget is exhausted."""
    # Build a summary of collected sources
    sources_summary = []
    for source in context.sources[:20]:
        sources_summary.append(f"- {source.title}: {source.snippet}")

    prompt = f"""Based on the research conducted so far, please provide a final report on: {query}

Sources found:
{chr(10).join(sources_summary)}

Please synthesize these findings into a structured markdown report with:
- Executive Summary
- Key Findings
- Detailed Analysis (based on available information)
- Sources cited inline
"""

    response = client.complete(
        messages=[Message(role="user", content=prompt)],
        use_smart_model=use_smart_model,
    )

    context.input_tokens += response.input_tokens
    context.output_tokens += response.output_tokens

    return response.content


def research_stream(
    query: str,
    strategy: Literal["breadth", "depth", "auto"] = "auto",
    max_sources: int = 10,
    search_types: list[str] | None = None,
    use_smart_model: bool = True,
    use_vectordb: bool = False,
    token_budget: int = 100000,
) -> Iterator[tuple[str, ResearchResult | None]]:
    """Stream research progress and results.

    Yields tuples of (message, result) where result is None until completion.

    Args:
        Same as research()

    Yields:
        Tuple of (progress_message, ResearchResult or None)
    """
    # Run research with progress tracking
    context = ResearchContext()

    if use_vectordb:
        yield ("Initializing vector database...", None)
        _init_vectordb(context)

    try:
        tools = get_research_tools(
            use_vectordb=context.vector_db is not None,
            search_types=search_types,
        )

        system_prompt = RESEARCH_SYSTEM_PROMPT.format(
            strategy=strategy,
            available_tools=_format_available_tools(tools),
            token_budget=token_budget,
            tokens_used=0,
        )

        context.messages = [
            Message(role="user", content=f"Research topic: {query}"),
        ]

        client = get_llm_client()
        report = ""

        yield (f"Starting research on: {query}", None)

        while True:
            total_tokens = context.input_tokens + context.output_tokens
            yield (f"Tokens used: {total_tokens:,}/{token_budget:,}", None)

            if total_tokens >= token_budget * 0.9:
                system_prompt += BUDGET_WARNING_PROMPT.format(
                    tokens_used=total_tokens,
                    token_budget=token_budget,
                )

            if total_tokens >= token_budget:
                yield ("Token budget reached, completing research...", None)
                report = _generate_forced_report(
                    query, context, client, use_smart_model
                )
                break

            response = client.complete(
                messages=context.messages,
                system=system_prompt,
                tools=tools,
                use_smart_model=use_smart_model,
            )

            context.input_tokens += response.input_tokens
            context.output_tokens += response.output_tokens

            if response.tool_calls:
                context.messages.append(
                    Message(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )

                for tool_call in response.tool_calls:
                    yield (f"Executing: {tool_call.name}", None)

                    if tool_call.name == "complete_research":
                        report = tool_call.arguments.get("report", "")
                        break

                    result = execute_tool(tool_call, context)
                    context.messages.append(
                        Message(role="tool", content="", tool_result=result)
                    )

                if report:
                    break
            else:
                context.messages.append(
                    Message(role="assistant", content=response.content)
                )
                if response.stop_reason == "end_turn":
                    context.messages.append(
                        Message(
                            role="user",
                            content="Please continue or call complete_research.",
                        )
                    )

    finally:
        if use_vectordb:
            _cleanup_vectordb(context)

    sources = context.sources[:max_sources]
    final_result = ResearchResult(
        query=query,
        report=report,
        sources=sources,
        input_tokens=context.input_tokens,
        output_tokens=context.output_tokens,
    )

    yield ("Research complete!", final_result)


# ============================================================================
# Save to Note
# ============================================================================


def append_research_to_note(
    result: ResearchResult,
    note_path: Path | str | None = None,
    notes_root: Path | None = None,
) -> Path:
    """Append research report to a note file.

    Args:
        result: The research result
        note_path: Target note path, or None for today's note
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

    # Build section
    section_title = f"## Research: {result.query}"

    # Append research
    if not content.endswith("\n"):
        content += "\n"
    content += f"\n{section_title}\n\n{result.report}\n"

    # Write back
    note_path.write_text(content, encoding="utf-8")

    return note_path
