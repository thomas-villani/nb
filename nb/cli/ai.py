"""AI-powered CLI commands.

Provides commands for LLM-enhanced note interactions including
question answering (RAG), summarization, and planning.
"""

from __future__ import annotations

import sys
from typing import Literal

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from nb.cli.completion import complete_notebook

console = Console()


# ============================================================================
# Plan Command Group
# ============================================================================


@click.group(name="plan")
def plan_group():
    """AI-assisted planning commands.

    Generate daily or weekly plans based on your todos, calendar,
    and recent notes. Plans can be refined interactively and saved
    to notes.

    Examples:

        nb plan week                     # Plan the upcoming week

        nb plan today                    # Plan or replan today

        nb plan week -n work             # Filter to work notebook todos

        nb plan week -o work             # Save plan to work notebook

        nb plan week --interactive       # Refine plan interactively
    """
    pass


@plan_group.command(name="week")
@click.option(
    "--notebook",
    "-n",
    "notebook",
    help="Filter todos to specific notebook.",
    shell_complete=complete_notebook,
)
@click.option(
    "--tag",
    "-t",
    "tag",
    help="Filter todos with this tag.",
)
@click.option(
    "--output",
    "-o",
    "output",
    is_flag=False,
    flag_value="today",
    default=None,
    help="Save plan to note. NOTEBOOK/NOTE for specific note, NOTEBOOK for new note, or 'today'.",
)
@click.option(
    "--prompt",
    "-p",
    "custom_prompt",
    help="Custom instructions for the plan.",
)
@click.option(
    "--no-calendar",
    is_flag=True,
    help="Skip calendar integration.",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Interactive mode to refine plan through conversation.",
)
@click.option(
    "--stream/--no-stream",
    default=True,
    help="Stream the response (default: stream).",
)
@click.option(
    "--smart/--fast",
    "use_smart",
    default=True,
    help="Use smart model (better) or fast model (cheaper). Default: smart.",
)
def plan_week_command(
    notebook: str | None,
    tag: str | None,
    output: str | None,
    custom_prompt: str | None,
    no_calendar: bool,
    interactive: bool,
    stream: bool,
    use_smart: bool,
) -> None:
    """Plan the upcoming week.

    Gathers incomplete todos, calendar events, and recent notes to
    generate a weekly plan with day-by-day breakdown.

    Examples:

        nb plan week

        nb plan week --notebook work --no-calendar

        nb plan week --interactive -o today

        nb plan week -o work                 # Save to new note in work

        nb plan week --prompt "Focus on urgent items only"
    """
    _run_planning(
        horizon="week",
        notebook=notebook,
        tag=tag,
        output=output,
        custom_prompt=custom_prompt,
        include_calendar=not no_calendar,
        interactive=interactive,
        stream=stream,
        use_smart=use_smart,
    )


@plan_group.command(name="today")
@click.option(
    "--notebook",
    "-n",
    "notebook",
    help="Filter todos to specific notebook.",
    shell_complete=complete_notebook,
)
@click.option(
    "--tag",
    "-t",
    "tag",
    help="Filter todos with this tag.",
)
@click.option(
    "--output",
    "-o",
    "output",
    is_flag=False,
    flag_value="today",
    default=None,
    help="Save plan to note. NOTEBOOK/NOTE for specific note, NOTEBOOK for new note, or 'today'.",
)
@click.option(
    "--prompt",
    "-p",
    "custom_prompt",
    help="Custom instructions for the plan.",
)
@click.option(
    "--no-calendar",
    is_flag=True,
    help="Skip calendar integration.",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Interactive mode to refine plan through conversation.",
)
@click.option(
    "--stream/--no-stream",
    default=True,
    help="Stream the response (default: stream).",
)
@click.option(
    "--smart/--fast",
    "use_smart",
    default=True,
    help="Use smart model (better) or fast model (cheaper). Default: smart.",
)
def plan_today_command(
    notebook: str | None,
    tag: str | None,
    output: str | None,
    custom_prompt: str | None,
    no_calendar: bool,
    interactive: bool,
    stream: bool,
    use_smart: bool,
) -> None:
    """Plan or replan today.

    Focuses on what can realistically be accomplished today based on
    your todos, calendar, and availability.

    Examples:

        nb plan today

        nb plan today --interactive

        nb plan today -o today --prompt "I have a meeting at 2pm"

        nb plan today -o work              # Save to new note in work
    """
    _run_planning(
        horizon="day",
        notebook=notebook,
        tag=tag,
        output=output,
        custom_prompt=custom_prompt,
        include_calendar=not no_calendar,
        interactive=interactive,
        stream=stream,
        use_smart=use_smart,
    )


def _run_planning(
    horizon: Literal["day", "week"],
    notebook: str | None,
    tag: str | None,
    output: str | None,
    custom_prompt: str | None,
    include_calendar: bool,
    interactive: bool,
    stream: bool,
    use_smart: bool,
) -> None:
    """Shared implementation for plan commands."""
    from datetime import date
    from pathlib import Path

    from nb.core.ai.planning import (
        PlanResult,
        PlanScope,
        append_plan_to_note,
        gather_planning_context,
    )
    from nb.core.llm import LLMConfigError, LLMError

    try:
        # Build scope
        scope = PlanScope(
            notebooks=[notebook] if notebook else None,
            tags=[tag] if tag else None,
        )

        # Gather context
        with console.status("[bold blue]Gathering planning context...[/bold blue]"):
            context = gather_planning_context(
                scope=scope,
                horizon=horizon,
                include_calendar=include_calendar,
            )

        # Display context summary
        _display_context_summary(context)

        plan_content = None
        if interactive:
            # Run interactive planning session
            _run_interactive_planning(context, use_smart, stream, output)
        else:
            # Generate plan directly
            if stream:
                plan_content = _run_streaming_plan(context, custom_prompt, use_smart)
            else:
                plan_content = _run_non_streaming_plan(
                    context, custom_prompt, use_smart
                )

            # Save to output if specified (non-interactive mode)
            if output and plan_content:
                if output == "today":
                    note_path = None  # Will use today's note
                elif "/" in output or output.endswith(".md"):
                    # Explicit path: NOTEBOOK/NOTE or path.md
                    note_path = Path(output)
                else:
                    # Just notebook name - create new note with date prefix
                    today = date.today().isoformat()
                    note_path = Path(output) / f"{today}-plan-{horizon}.md"

                plan_result = PlanResult(horizon=horizon, raw_response=plan_content)
                saved_path = append_plan_to_note(plan_result, note_path=note_path)
                console.print(f"\n[green]Plan saved to {saved_path}[/green]")

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


def _display_context_summary(context) -> None:
    """Display a summary of the planning context."""
    from nb.core.ai.planning import PlanningContext

    ctx: PlanningContext = context

    # Build summary table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value")

    table.add_row("Horizon", ctx.horizon)
    table.add_row("Total todos", str(len(ctx.todos)))

    if ctx.overdue_todos:
        table.add_row("Overdue", f"[red]{len(ctx.overdue_todos)}[/red]")
    if ctx.in_progress_todos:
        table.add_row("In progress", f"[yellow]{len(ctx.in_progress_todos)}[/yellow]")
    if ctx.calendar_events:
        table.add_row("Calendar events", str(len(ctx.calendar_events)))
    if ctx.availability_blocks:
        total_mins = sum(b.duration_minutes for b in ctx.availability_blocks)
        table.add_row("Available time", f"~{total_mins // 60}h {total_mins % 60}m")

    console.print(
        Panel(table, title="[bold]Planning Context[/bold]", border_style="blue")
    )
    console.print()


def _run_streaming_plan(context, custom_prompt: str | None, use_smart: bool) -> str:
    """Run streaming plan generation. Returns the plan content."""
    from nb.core.ai.planning import generate_plan_stream

    console.print("[bold]Generating plan...[/bold]")
    console.print()

    full_response = ""
    for chunk in generate_plan_stream(
        context,
        use_smart_model=use_smart,
        custom_prompt=custom_prompt,
    ):
        if chunk.content:
            console.print(chunk.content, end="")
            full_response += chunk.content

        if chunk.is_final and (chunk.input_tokens or chunk.output_tokens):
            console.print()
            console.print(
                f"\n[dim]Tokens: {chunk.input_tokens} in, {chunk.output_tokens} out[/dim]"
            )

    return full_response


def _run_non_streaming_plan(context, custom_prompt: str | None, use_smart: bool) -> str:
    """Run non-streaming plan generation. Returns the plan content."""
    from nb.core.ai.planning import generate_plan

    with console.status("[bold blue]Generating plan...[/bold blue]"):
        result = generate_plan(
            context,
            use_smart_model=use_smart,
            custom_prompt=custom_prompt,
        )

    console.print(Markdown(result.raw_response))

    if result.input_tokens or result.output_tokens:
        console.print(
            f"\n[dim]Tokens: {result.input_tokens} in, {result.output_tokens} out[/dim]"
        )

    return result.raw_response


def _run_interactive_planning(
    context, use_smart: bool, stream: bool, output: str | None
) -> None:
    """Run interactive planning session."""
    from datetime import date
    from pathlib import Path

    from nb.core.ai.planning import (
        PlanResult,
        append_plan_to_note,
        continue_planning_session,
        continue_planning_session_stream,
        create_planning_session,
    )

    def _resolve_output_path(output_val: str | None) -> Path | None:
        """Resolve output value to a Path or None for today's note."""
        if output_val is None or output_val == "today":
            return None  # Will use today's note
        elif "/" in output_val or output_val.endswith(".md"):
            return Path(output_val)
        else:
            # Just notebook name - create new note with date prefix
            today = date.today().isoformat()
            return Path(output_val) / f"{today}-plan-{context.horizon}.md"

    session = create_planning_session(context)

    console.print("[bold]Interactive Planning Mode[/bold]")
    console.print("[dim]Type your requests to refine the plan. Commands:[/dim]")
    console.print("[dim]  save - Save current plan to note[/dim]")
    console.print("[dim]  done/quit/exit - Finish and exit[/dim]")
    console.print()

    # Generate initial plan
    initial_prompt = "Please create an initial plan based on the context provided."

    if stream:
        console.print("[bold cyan]Assistant:[/bold cyan] ", end="")
        for chunk_content, _result in continue_planning_session_stream(
            session, initial_prompt, use_smart_model=use_smart
        ):
            if chunk_content:
                console.print(chunk_content, end="")
        console.print()
    else:
        with console.status("[bold blue]Generating initial plan...[/bold blue]"):
            response, _result = continue_planning_session(
                session, initial_prompt, use_smart_model=use_smart
            )
        console.print("[bold cyan]Assistant:[/bold cyan]")
        console.print(Markdown(response))

    # Interactive loop
    while True:
        console.print()
        try:
            user_input = console.input("[bold green]You:[/bold green] ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Check for commands
        lower_input = user_input.lower()
        if lower_input in ("done", "quit", "exit", "q"):
            break

        if lower_input == "save":
            if session.current_plan:
                plan = PlanResult(
                    horizon=context.horizon,
                    raw_response=session.current_plan,
                )
                note_path = _resolve_output_path(output)
                saved_path = append_plan_to_note(plan, note_path=note_path)
                console.print(f"[green]Plan saved to {saved_path}[/green]")
            else:
                console.print("[yellow]No plan to save yet.[/yellow]")
            continue

        # Continue conversation
        if stream:
            console.print("[bold cyan]Assistant:[/bold cyan] ", end="")
            for chunk_content, _result in continue_planning_session_stream(
                session, user_input, use_smart_model=use_smart
            ):
                if chunk_content:
                    console.print(chunk_content, end="")
            console.print()
        else:
            with console.status("[bold blue]Thinking...[/bold blue]"):
                response, _result = continue_planning_session(
                    session, user_input, use_smart_model=use_smart
                )
            console.print("[bold cyan]Assistant:[/bold cyan]")
            console.print(Markdown(response))

    # Offer to save on exit if output was specified or if there's a plan
    if session.current_plan:
        console.print()
        if output:
            # Auto-save if output was specified
            save = console.input(f"[dim]Save plan to {output}? [Y/n]:[/dim] ")
            if save.lower() not in ("n", "no"):
                plan = PlanResult(
                    horizon=context.horizon,
                    raw_response=session.current_plan,
                )
                note_path = _resolve_output_path(output)
                saved_path = append_plan_to_note(plan, note_path=note_path)
                console.print(f"[green]Plan saved to {saved_path}[/green]")
        else:
            save = console.input("[dim]Save plan to today's note? [y/N]:[/dim] ")
            if save.lower() in ("y", "yes"):
                plan = PlanResult(
                    horizon=context.horizon,
                    raw_response=session.current_plan,
                )
                saved_path = append_plan_to_note(plan)
                console.print(f"[green]Plan saved to {saved_path}[/green]")


# ============================================================================
# Ask Command
# ============================================================================


@click.command(name="ask")
@click.argument("question")
@click.option(
    "--notebook",
    "-n",
    "notebook",
    help="Filter to specific notebook",
    shell_complete=complete_notebook,
)
@click.option(
    "-N",
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
@click.option(
    "--agentic/--no-agentic",
    default=False,
    help="Use agentic mode with tool-calling for complex queries (e.g., todo lookups).",
)
@click.option(
    "--max-tool-calls",
    default=5,
    type=int,
    help="Maximum tool calls in agentic mode (default: 5).",
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
    agentic: bool,
    max_tool_calls: int,
) -> None:
    """Ask a question about your notes using AI.

    Uses RAG (Retrieval Augmented Generation) to find relevant notes
    and generate an answer based on their content.

    Use --agentic for complex queries that need to query todos or search
    multiple times.

    Examples:

        nb ask "what did we decide about the API design?"

        nb ask "summarize project X" --notebook work

        nb ask "what server version?" -N work/deploy-notes

        nb ask "who owns deployment?" --tag infrastructure

        nb ask "what remains to be done for the widget project?" --agentic

        nb ask "what are my overdue tasks?" --agentic
    """
    from nb.core.llm import LLMConfigError, LLMError

    try:
        if agentic:
            # Use agentic mode with tool-calling
            if stream:
                _ask_agentic_streaming(
                    question=question,
                    notebook=notebook,
                    tag=tag,
                    show_sources=show_sources,
                    use_smart=use_smart,
                    max_results=max_results,
                    max_tool_calls=max_tool_calls,
                )
            else:
                _ask_agentic_non_streaming(
                    question=question,
                    notebook=notebook,
                    tag=tag,
                    show_sources=show_sources,
                    use_smart=use_smart,
                    max_results=max_results,
                    max_tool_calls=max_tool_calls,
                )
        elif stream:
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


def _ask_agentic_streaming(
    question: str,
    notebook: str | None,
    tag: str | None,
    show_sources: bool,
    use_smart: bool,
    max_results: int,
    max_tool_calls: int,
) -> None:
    """Handle streaming agentic ask response."""
    from nb.core.ai.ask_agentic import ask_notes_agentic_stream

    console.print("[dim]Starting agentic search...[/dim]")

    result = None
    for message, final_result in ask_notes_agentic_stream(
        question=question,
        notebook=notebook,
        tag=tag,
        max_context_results=max_results,
        max_tool_calls=max_tool_calls,
        use_smart_model=use_smart,
    ):
        if final_result is not None:
            result = final_result
        else:
            console.print(f"[dim]{message}[/dim]")

    if result is None:
        console.print("[yellow]No result returned[/yellow]")
        return

    # Show sources if requested
    if show_sources and result.sources:
        console.print()
        _display_sources(result.sources)
        console.print()

    # Show the answer
    console.print("[bold]Answer:[/bold]")
    console.print(Markdown(result.answer))

    # Show metadata
    tool_info = ""
    if result.tools_used:
        tool_info = f", tools: {', '.join(result.tools_used)}"
    console.print(
        f"\n[dim]Tokens: {result.input_tokens} in, {result.output_tokens} out | "
        f"Tool calls: {result.tool_calls}{tool_info}[/dim]"
    )


def _ask_agentic_non_streaming(
    question: str,
    notebook: str | None,
    tag: str | None,
    show_sources: bool,
    use_smart: bool,
    max_results: int,
    max_tool_calls: int,
) -> None:
    """Handle non-streaming agentic ask response."""
    from nb.core.ai.ask_agentic import ask_notes_agentic

    progress_messages = []

    def progress_callback(msg: str) -> None:
        progress_messages.append(msg)

    with console.status("[bold blue]Thinking...[/bold blue]") as status:
        result = ask_notes_agentic(
            question=question,
            notebook=notebook,
            tag=tag,
            max_context_results=max_results,
            max_tool_calls=max_tool_calls,
            use_smart_model=use_smart,
            progress_callback=lambda msg: status.update(
                f"[bold blue]{msg}[/bold blue]"
            ),
        )

    # Show sources if requested
    if show_sources and result.sources:
        _display_sources(result.sources)
        console.print()

    # Show the answer
    console.print("[bold]Answer:[/bold]")
    console.print(Markdown(result.answer))

    # Show metadata
    tool_info = ""
    if result.tools_used:
        tool_info = f", tools: {', '.join(result.tools_used)}"
    console.print(
        f"\n[dim]Tokens: {result.input_tokens} in, {result.output_tokens} out | "
        f"Tool calls: {result.tool_calls}{tool_info}[/dim]"
    )


# ============================================================================
# Summarize Command
# ============================================================================


def summarize_options(f):
    """Shared options for summarize and tldr commands."""
    # Apply options in reverse order (Click decorator stacking)
    f = click.option(
        "--smart/--fast",
        "use_smart",
        default=True,
        help="Use smart model (better) or fast model (cheaper). Default: smart.",
    )(f)
    f = click.option(
        "--stream/--no-stream",
        default=True,
        help="Stream the response (default: stream).",
    )(f)
    f = click.option(
        "--prompt",
        "-p",
        "custom_prompt",
        help="Custom instructions for the summary.",
    )(f)
    f = click.option(
        "--front-matter",
        "-fm",
        is_flag=True,
        help="Store summary in source note's YAML frontmatter.",
    )(f)
    f = click.option(
        "--output",
        "-o",
        "output",
        is_flag=False,
        flag_value="today",
        default=None,
        help="Save output to note. NOTEBOOK/NOTE for specific note, NOTEBOOK for new note, or 'today'.",
    )(f)
    f = click.option(
        "--days",
        "-d",
        type=int,
        help="Limit to last N days (for notebook/tag summaries).",
    )(f)
    f = click.option(
        "--tag",
        "-t",
        help="Filter to notes with this tag.",
    )(f)
    f = click.option(
        "--notebook",
        "-n",
        "notebook",
        help="Filter to notes from this notebook.",
        shell_complete=complete_notebook,
    )(f)
    f = click.argument("target", required=False)(f)
    return f


@click.command(name="summarize")
@summarize_options
def summarize_command(
    target: str | None,
    notebook: str | None,
    tag: str | None,
    days: int | None,
    output: str | None,
    front_matter: bool,
    custom_prompt: str | None,
    stream: bool,
    use_smart: bool,
) -> None:
    """Summarize notes with AI.

    Generates a comprehensive summary of one or more notes.

    Examples:

        nb summarize                      # Summarize today's note

        nb summarize yesterday            # Summarize yesterday's note

        nb summarize work                 # Summarize all notes in work notebook

        nb summarize work/meeting-notes   # Summarize specific note

        nb summarize --tag project-x      # Summarize notes with tag

        nb summarize work --days 7        # Week summary for notebook

        nb summarize -o today             # Save to today's note

        nb summarize -o work              # Save to new note in work notebook

        nb summarize --front-matter       # Store in source's frontmatter
    """
    _run_summarize(
        target=target,
        notebook=notebook,
        tag=tag,
        days=days,
        output=output,
        front_matter=front_matter,
        custom_prompt=custom_prompt,
        stream=stream,
        use_smart=use_smart,
        mode="summarize",
    )


@click.command(name="tldr")
@summarize_options
def tldr_command(
    target: str | None,
    notebook: str | None,
    tag: str | None,
    days: int | None,
    output: str | None,
    front_matter: bool,
    custom_prompt: str | None,
    stream: bool,
    use_smart: bool,
) -> None:
    """Quick 1-2 sentence summary of notes.

    Like 'summarize' but produces ultra-brief summaries.

    Examples:

        nb tldr                           # TLDR today's note

        nb tldr work --days 7             # Week TLDR for work

        nb tldr --tag meeting             # TLDR meeting notes

        nb tldr -o work                   # Save TLDR to new note in work
    """
    _run_summarize(
        target=target,
        notebook=notebook,
        tag=tag,
        days=days,
        output=output,
        front_matter=front_matter,
        custom_prompt=custom_prompt,
        stream=stream,
        use_smart=use_smart,
        mode="tldr",
    )


def _run_summarize(
    target: str | None,
    notebook: str | None,
    tag: str | None,
    days: int | None,
    output: str | None,
    front_matter: bool,
    custom_prompt: str | None,
    stream: bool,
    use_smart: bool,
    mode: Literal["summarize", "tldr"],
) -> None:
    """Shared implementation for summarize and tldr commands."""
    from datetime import date
    from pathlib import Path

    from nb.core.ai.summarize import (
        append_summary_to_note,
        resolve_target,
        update_note_frontmatter_summary,
    )
    from nb.core.clip import slugify
    from nb.core.llm import LLMConfigError, LLMError

    try:
        # Resolve target to notes
        with console.status("[bold blue]Finding notes to summarize...[/bold blue]"):
            resolved = resolve_target(
                target=target,
                notebook=notebook,
                tag=tag,
                days=days,
            )

        if not resolved.notes:
            console.print("[yellow]No notes found to summarize.[/yellow]")
            sys.exit(1)

        # Display what we're summarizing
        console.print(
            f"[dim]Summarizing: {resolved.description} ({len(resolved.notes)} note(s))[/dim]"
        )
        console.print()

        # Single note vs multi-note handling
        if len(resolved.notes) == 1:
            # Single note - direct summarization
            result = _summarize_single_note(
                resolved.notes[0],
                mode=mode,
                custom_prompt=custom_prompt,
                stream=stream,
                use_smart=use_smart,
            )
        else:
            # Multi-note - map-reduce
            result = _summarize_multiple_notes(
                resolved,
                mode=mode,
                custom_prompt=custom_prompt,
                use_smart=use_smart,
            )

        # Handle --front-matter: update source note(s)
        if front_matter:
            for note in resolved.notes:
                # Find individual summary for this note
                individual = next(
                    (s for s in result.individual_summaries if s.path == note.path),
                    None,
                )
                summary_text = individual.summary if individual else result.summary
                update_note_frontmatter_summary(note.path, summary_text)
            console.print(
                f"\n[green]Updated frontmatter in {len(resolved.notes)} note(s)[/green]"
            )

        # Handle --output: save to output note
        if output:
            if output == "today":
                note_path = None  # Will use today's note
            elif "/" in output or output.endswith(".md"):
                # Explicit path: NOTEBOOK/NOTE or path.md
                note_path = Path(output)
            else:
                # Just notebook name - create new note with date prefix
                today = date.today().isoformat()
                slug = slugify(resolved.description)
                note_path = Path(output) / f"{today}-summary-{slug}.md"

            saved_path = append_summary_to_note(
                result.summary,
                resolved.description,
                note_path=note_path,
            )
            console.print(f"\n[green]Summary saved to {saved_path}[/green]")

        # Token usage
        if result.input_tokens or result.output_tokens:
            console.print(
                f"\n[dim]Tokens: {result.input_tokens} in, {result.output_tokens} out[/dim]"
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


def _summarize_single_note(
    note,
    mode: Literal["summarize", "tldr"],
    custom_prompt: str | None,
    stream: bool,
    use_smart: bool,
):
    """Summarize a single note, handling streaming vs non-streaming."""
    from nb.core.ai.summarize import (
        NoteSummary,
        SummarizeResult,
        summarize_note,
        summarize_note_stream,
    )

    if stream:
        console.print(f"[bold]{'TLDR' if mode == 'tldr' else 'Summary'}:[/bold]")
        full_response = ""
        final_chunk = None

        for chunk in summarize_note_stream(
            note,
            mode=mode,
            custom_prompt=custom_prompt,
            use_smart_model=use_smart,
        ):
            if chunk.content:
                console.print(chunk.content, end="")
                full_response += chunk.content
            if chunk.is_final:
                final_chunk = chunk

        console.print()  # Final newline

        return SummarizeResult(
            summary=full_response,
            sources=[note],
            individual_summaries=[
                NoteSummary(
                    path=note.path,
                    title=note.title,
                    summary=full_response,
                    notebook=note.notebook,
                )
            ],
            input_tokens=final_chunk.input_tokens if final_chunk else 0,
            output_tokens=final_chunk.output_tokens if final_chunk else 0,
        )
    else:
        with console.status(
            f"[bold blue]Generating {'TLDR' if mode == 'tldr' else 'summary'}...[/bold blue]"
        ):
            summary = summarize_note(
                note,
                mode=mode,
                custom_prompt=custom_prompt,
                use_smart_model=use_smart,
            )

        console.print(f"[bold]{'TLDR' if mode == 'tldr' else 'Summary'}:[/bold]")
        console.print(Markdown(summary.summary))

        # We don't have token info from non-streaming single note
        return SummarizeResult(
            summary=summary.summary,
            sources=[note],
            individual_summaries=[summary],
        )


def _summarize_multiple_notes(
    target,
    mode: Literal["summarize", "tldr"],
    custom_prompt: str | None,
    use_smart: bool,
):
    """Summarize multiple notes using map-reduce."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from nb.core.ai.summarize import summarize_notes_map_reduce

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[bold blue]Summarizing {len(target.notes)} notes...[/bold blue]",
            total=len(target.notes),
        )

        def update_progress(current, total, title):
            progress.update(
                task,
                description=f"[bold blue]Summarizing ({current}/{total}): {title}[/bold blue]",
                completed=current,
            )

        result = summarize_notes_map_reduce(
            target,
            mode=mode,
            custom_prompt=custom_prompt,
            use_smart_model=use_smart,
            progress_callback=update_progress,
        )

    console.print(f"\n[bold]{'TLDR' if mode == 'tldr' else 'Summary'}:[/bold]")
    console.print(Markdown(result.summary))

    return result


# ============================================================================
# Research Command
# ============================================================================


@click.command(name="research")
@click.argument("query")
@click.option(
    "--output",
    "-o",
    "output",
    is_flag=False,
    flag_value="today",
    default=None,
    help="Save report to note. NOTEBOOK/NOTE for specific note, NOTEBOOK for new note, or 'today'.",
)
@click.option(
    "--search",
    "-s",
    "search_types",
    multiple=True,
    type=click.Choice(["web", "news", "scholar", "patents"]),
    help="Restrict to specific search types. Can be repeated.",
)
@click.option(
    "--max-sources",
    "-k",
    default=10,
    type=int,
    help="Maximum sources to include in result (default: 10).",
)
@click.option(
    "--strategy",
    type=click.Choice(["breadth", "depth", "auto"]),
    default="auto",
    help="Research strategy (default: auto).",
)
@click.option(
    "--token-budget",
    default=100000,
    type=int,
    help="Maximum tokens to consume (default: 100000).",
)
@click.option(
    "--use-vectordb/--no-vectordb",
    default=False,
    help="Use vector DB for context management (default: no).",
)
@click.option(
    "--stream/--no-stream",
    default=True,
    help="Stream progress (default: stream).",
)
@click.option(
    "--smart/--fast",
    "use_smart",
    default=True,
    help="Use smart model (better) or fast model (cheaper). Default: smart.",
)
def research_command(
    query: str,
    output: str | None,
    search_types: tuple[str, ...],
    max_sources: int,
    strategy: Literal["breadth", "depth", "auto"],
    token_budget: int,
    use_vectordb: bool,
    stream: bool,
    use_smart: bool,
) -> None:
    """Research a topic using web search and AI analysis.

    Uses an AI agent to search the web, fetch content, and generate
    a comprehensive research report.

    Requires SERPER_API_KEY environment variable for web search.

    Examples:

        nb research "CoolCo 2025 Q4 financial results"

        nb research "AI trends 2025" -o today

        nb research "climate change policies" -o work

        nb research "machine learning" --search scholar --use-vectordb

        nb research "market analysis" --strategy depth --token-budget 200000
    """
    from nb.core.llm import LLMConfigError, LLMError
    from nb.core.search import SearchAPIError

    # Convert tuple to list, or None if empty
    search_list = list(search_types) if search_types else None

    try:
        if stream:
            _research_streaming(
                query=query,
                strategy=strategy,
                max_sources=max_sources,
                search_types=search_list,
                use_smart=use_smart,
                use_vectordb=use_vectordb,
                token_budget=token_budget,
                output=output,
            )
        else:
            _research_non_streaming(
                query=query,
                strategy=strategy,
                max_sources=max_sources,
                search_types=search_list,
                use_smart=use_smart,
                use_vectordb=use_vectordb,
                token_budget=token_budget,
                output=output,
            )
    except LLMConfigError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        console.print(
            "\n[dim]Hint: Set ANTHROPIC_API_KEY environment variable or configure "
            "with 'nb config set llm.api_key <key>'[/dim]"
        )
        sys.exit(1)
    except SearchAPIError as e:
        console.print(f"[red]Search API error:[/red] {e}")
        console.print(
            "\n[dim]Hint: Set SERPER_API_KEY environment variable. "
            "Get a key at https://serper.dev[/dim]"
        )
        sys.exit(1)
    except LLMError as e:
        console.print(f"[red]LLM error:[/red] {e}")
        sys.exit(1)
    except ValueError as e:
        console.print(f"[yellow]{e}[/yellow]")
        sys.exit(1)


def _research_streaming(
    query: str,
    strategy: Literal["breadth", "depth", "auto"],
    max_sources: int,
    search_types: list[str] | None,
    use_smart: bool,
    use_vectordb: bool,
    token_budget: int,
    output: str | None,
) -> None:
    """Handle streaming research with progress updates."""
    from nb.core.ai.research import append_research_to_note, research_stream

    console.print(f"[bold]Researching:[/bold] {query}")
    console.print(f"[dim]Strategy: {strategy}, Token budget: {token_budget:,}[/dim]")
    console.print()

    result = None
    for message, res in research_stream(
        query=query,
        strategy=strategy,
        max_sources=max_sources,
        search_types=search_types,
        use_smart_model=use_smart,
        use_vectordb=use_vectordb,
        token_budget=token_budget,
    ):
        console.print(f"[dim]{message}[/dim]")
        if res is not None:
            result = res

    if result is None:
        console.print("[red]Research failed - no result returned[/red]")
        sys.exit(1)

    # Display results
    _display_research_result(result)

    # Save to note if requested via --output
    if output:
        from datetime import date
        from pathlib import Path

        from nb.core.clip import slugify

        if output == "today":
            target = None  # Will use today's note
        elif "/" in output or output.endswith(".md"):
            # Explicit path: NOTEBOOK/NOTE or path.md
            target = output
        else:
            # Just notebook name - create new note with date prefix
            today = date.today().isoformat()
            slug = slugify(query)
            target = str(Path(output) / f"{today}-research-{slug}.md")

        saved_path = append_research_to_note(result, target)
        console.print(f"\n[green]Report saved to:[/green] {saved_path}")


def _research_non_streaming(
    query: str,
    strategy: Literal["breadth", "depth", "auto"],
    max_sources: int,
    search_types: list[str] | None,
    use_smart: bool,
    use_vectordb: bool,
    token_budget: int,
    output: str | None,
) -> None:
    """Handle non-streaming research."""
    from nb.core.ai.research import append_research_to_note, research

    def progress_cb(msg: str) -> None:
        console.print(f"[dim]{msg}[/dim]")

    console.print(f"[bold]Researching:[/bold] {query}")
    console.print(f"[dim]Strategy: {strategy}, Token budget: {token_budget:,}[/dim]")
    console.print()

    with console.status("[bold blue]Researching...[/bold blue]"):
        result = research(
            query=query,
            strategy=strategy,
            max_sources=max_sources,
            search_types=search_types,
            use_smart_model=use_smart,
            use_vectordb=use_vectordb,
            token_budget=token_budget,
            progress_callback=progress_cb,
        )

    # Display results
    _display_research_result(result)

    # Save to note if requested via --output
    if output:
        from datetime import date
        from pathlib import Path

        from nb.core.clip import slugify

        if output == "today":
            target = None  # Will use today's note
        elif "/" in output or output.endswith(".md"):
            # Explicit path: NOTEBOOK/NOTE or path.md
            target = output
        else:
            # Just notebook name - create new note with date prefix
            today = date.today().isoformat()
            slug = slugify(query)
            target = str(Path(output) / f"{today}-research-{slug}.md")

        saved_path = append_research_to_note(result, target)
        console.print(f"\n[green]Report saved to:[/green] {saved_path}")


def _display_research_result(result) -> None:
    """Display research result with sources and report."""
    # Display sources
    if result.sources:
        source_lines = []
        for i, src in enumerate(result.sources[:10], 1):
            line = f"[bold]{i}.[/bold] {src.title}"
            if src.fetched:
                line += " [green]✓[/green]"
            line += f"\n   [dim]{src.url}[/dim]"
            source_lines.append(line)

        console.print(
            Panel(
                "\n".join(source_lines),
                title="[bold]Sources[/bold]",
                border_style="blue",
                padding=(0, 1),
            )
        )
        console.print()

    # Display report
    console.print("[bold]Research Report:[/bold]")
    console.print(Markdown(result.report))

    # Show token usage
    console.print(
        f"\n[dim]Tokens: {result.input_tokens:,} in, {result.output_tokens:,} out[/dim]"
    )


def register_ai_commands(cli: click.Group) -> None:
    """Register AI commands with the main CLI."""
    cli.add_command(ask_command)
    cli.add_command(plan_group)
    cli.add_command(summarize_command)
    cli.add_command(tldr_command)
    cli.add_command(research_command)
