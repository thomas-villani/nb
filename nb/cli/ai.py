"""AI-powered CLI commands.

Provides commands for LLM-enhanced note interactions including
question answering (RAG), summarization, and planning.
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from nb.cli.completion import complete_notebook

console = Console()


@click.command(name="ask")
@click.argument("question")
@click.option(
    "--notebook",
    "-b",
    "notebook",
    help="Filter to specific notebook",
    shell_complete=complete_notebook,
)
@click.option(
    "-n",
    "--note",
    "note_path",
    help="Ask about a specific note instead of searching.",
)
@click.option(
    "-t",
    "--tag",
    help="Filter to notes with this tag.",
)
@click.option(
    "--stream/--no-stream",
    default=True,
    help="Stream the response (default: stream).",
)
@click.option(
    "--show-sources/--no-sources",
    default=True,
    help="Show source notes used (default: show).",
)
@click.option(
    "--smart/--fast",
    "use_smart",
    default=True,
    help="Use smart model (better) or fast model (cheaper). Default: smart.",
)
@click.option(
    "--max-results",
    "-k",
    default=5,
    type=int,
    help="Maximum number of documents to retrieve (default: 5).",
)
@click.option(
    "--context-window",
    default=3,
    type=int,
    help="Number of similar chunks to include per match (default: 3).",
)
def ask_command(
    question: str,
    notebook: str | None,
    note_path: str | None,
    tag: str | None,
    stream: bool,
    show_sources: bool,
    use_smart: bool,
    max_results: int,
    context_window: int,
) -> None:
    """Ask a question about your notes using AI.

    Uses RAG (Retrieval Augmented Generation) to find relevant notes
    and generate an answer based on their content.

    Examples:

        nb ask "what did we decide about the API design?"

        nb ask "summarize project X" --notebook work

        nb ask "what server version?" -n work/deploy-notes

        nb ask "who owns deployment?" --tag infrastructure
    """
    from nb.core.llm import LLMConfigError, LLMError

    try:
        if stream:
            _ask_streaming(
                question=question,
                notebook=notebook,
                note_path=note_path,
                tag=tag,
                show_sources=show_sources,
                use_smart=use_smart,
                max_results=max_results,
                context_window=context_window,
            )
        else:
            _ask_non_streaming(
                question=question,
                notebook=notebook,
                note_path=note_path,
                tag=tag,
                show_sources=show_sources,
                use_smart=use_smart,
                max_results=max_results,
                context_window=context_window,
            )
    except LLMConfigError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        console.print(
            "\n[dim]Hint: Set ANTHROPIC_API_KEY environment variable or configure "
            "with 'nb config set llm.api_key <key>'[/dim]"
        )
        sys.exit(1)
    except LLMError as e:
        console.print(f"[red]LLM error:[/red] {e}")
        sys.exit(1)
    except ValueError as e:
        console.print(f"[yellow]{e}[/yellow]")
        sys.exit(1)


def _ask_streaming(
    question: str,
    notebook: str | None,
    note_path: str | None,
    tag: str | None,
    show_sources: bool,
    use_smart: bool,
    max_results: int,
    context_window: int,
) -> None:
    """Handle streaming ask response."""
    from nb.core.ai.ask import ask_notes_stream

    # Show what we're searching
    search_desc = []
    if notebook:
        search_desc.append(f"notebook: {notebook}")
    if note_path:
        search_desc.append(f"note: {note_path}")
    if tag:
        search_desc.append(f"tag: {tag}")

    if search_desc:
        console.print(f"[dim]Searching {', '.join(search_desc)}...[/dim]")
    else:
        console.print("[dim]Searching all notes...[/dim]")

    # Get sources and stream
    sources, stream = ask_notes_stream(
        question=question,
        notebook=notebook,
        note_path=note_path,
        tag=tag,
        max_context_results=max_results,
        context_window=context_window,
        use_smart_model=use_smart,
    )

    # Show sources first if requested
    if show_sources and sources:
        console.print()
        _display_sources(sources)
        console.print()

    # Stream the response
    console.print("[bold]Answer:[/bold]")
    full_response = ""
    for chunk in stream:
        if chunk.content:
            console.print(chunk.content, end="")
            full_response += chunk.content

    console.print()  # Final newline

    # Show token usage at end
    if chunk.is_final and (chunk.input_tokens or chunk.output_tokens):
        console.print(
            f"\n[dim]Tokens: {chunk.input_tokens} in, {chunk.output_tokens} out[/dim]"
        )


def _ask_non_streaming(
    question: str,
    notebook: str | None,
    note_path: str | None,
    tag: str | None,
    show_sources: bool,
    use_smart: bool,
    max_results: int,
    context_window: int,
) -> None:
    """Handle non-streaming ask response."""
    from nb.core.ai.ask import ask_notes

    with console.status("[bold blue]Thinking...[/bold blue]"):
        result = ask_notes(
            question=question,
            notebook=notebook,
            note_path=note_path,
            tag=tag,
            max_context_results=max_results,
            context_window=context_window,
            use_smart_model=use_smart,
        )

    # Show sources if requested
    if show_sources and result.sources:
        _display_sources(result.sources)
        console.print()

    # Show the answer
    console.print("[bold]Answer:[/bold]")
    console.print(Markdown(result.answer))

    # Show token usage
    if result.input_tokens or result.output_tokens:
        console.print(
            f"\n[dim]Tokens: {result.input_tokens} in, {result.output_tokens} out[/dim]"
        )


def _display_sources(sources: list) -> None:
    """Display source references in a panel."""
    from nb.core.ai.ask import NoteReference

    source_lines = []
    for i, src in enumerate(sources, 1):
        if isinstance(src, NoteReference):
            display_name = src.title or src.path
            score_pct = int(src.score * 100)
            line = f"[bold]{i}.[/bold] {display_name}"
            if src.notebook:
                line += f" [dim]({src.notebook})[/dim]"
            line += f" [cyan]{score_pct}%[/cyan]"
            source_lines.append(line)

    if source_lines:
        sources_text = "\n".join(source_lines)
        console.print(
            Panel(
                sources_text,
                title="[bold]Sources[/bold]",
                border_style="blue",
                padding=(0, 1),
            )
        )


def register_ai_commands(cli: click.Group) -> None:
    """Register AI commands with the main CLI."""
    cli.add_command(ask_command)
