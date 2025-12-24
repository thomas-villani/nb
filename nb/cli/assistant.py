"""AI Executive Assistant CLI command.

Interactive conversational interface for managing todos and notes
with confirmation flow for write operations.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from nb.cli.completion import complete_notebook

console = Console()


@click.command(name="assistant")
@click.argument("query", required=False)
@click.option(
    "--notebook",
    "-n",
    "notebook",
    help="Focus context on specific notebook.",
    shell_complete=complete_notebook,
)
@click.option(
    "--file",
    "-f",
    "files",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Include file(s) as context (can be repeated).",
)
@click.option(
    "--paste",
    is_flag=True,
    help="Include clipboard content as context.",
)
@click.option(
    "--note",
    "-N",
    "notes",
    multiple=True,
    help="Include specific note(s) as context (notebook/note format, can be repeated).",
)
@click.option(
    "--no-calendar",
    is_flag=True,
    help="Skip calendar integration.",
)
@click.option(
    "--smart/--fast",
    "use_smart",
    default=True,
    help="Use smart model (better) or fast model (cheaper). Default: smart.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show proposed changes without executing them.",
)
@click.option(
    "--token-budget",
    type=int,
    default=100000,
    help="Maximum tokens to consume per session.",
)
@click.option(
    "--max-tools",
    type=int,
    default=10,
    help="Maximum tool calls per turn.",
)
def assistant_command(
    query: str | None,
    notebook: str | None,
    files: tuple[Path, ...],
    paste: bool,
    notes: tuple[str, ...],
    no_calendar: bool,
    use_smart: bool,
    dry_run: bool,
    token_budget: int,
    max_tools: int,
) -> None:
    """AI Executive Assistant for task and note management.

    An interactive agent that can analyze your todos, notes, and calendar,
    and take action on your behalf. Write operations require confirmation.

    Optionally provide an initial QUERY to start the conversation.

    \b
    Examples:
        nb assistant
        > reschedule the todos for later this week to monday next week
        nb assistant -n work
        > give me a status update on the project
        nb assistant "add 3 todos for the quarterly review"
        nb assistant --paste "Here's my plan for today"
        nb assistant -f plan.md "Review this plan and add todos to work"
        nb assistant -N work/project "Summarize the current status"
        nb assistant --dry-run
        > add 3 todos for the quarterly review
    """
    from nb.core.llm import LLMConfigError, LLMError

    # Gather additional context from files, clipboard, and notes
    additional_context = _gather_additional_context(files, paste, notes)

    try:
        _run_assistant_interactive(
            notebook=notebook,
            include_calendar=not no_calendar,
            use_smart=use_smart,
            dry_run=dry_run,
            token_budget=token_budget,
            max_tools=max_tools,
            initial_query=query,
            additional_context=additional_context,
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


def _gather_additional_context(
    files: tuple[Path, ...],
    paste: bool,
    notes: tuple[str, ...],
) -> str:
    """Gather additional context from files, clipboard, and notes.

    Args:
        files: Paths to files to include as context.
        paste: Whether to include clipboard content.
        notes: Note references to include (notebook/note format).

    Returns:
        Formatted context string, or empty string if no additional context.
    """
    from nb.cli.utils import resolve_note_ref

    parts: list[str] = []

    # Read files
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8")
            parts.append(f"## FILE: {file_path.name}\n\n```\n{content}\n```")
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not read file {file_path}: {e}[/yellow]"
            )

    # Read clipboard
    if paste:
        try:
            import pyperclip

            clipboard_content = pyperclip.paste()
            if clipboard_content and clipboard_content.strip():
                parts.append(f"## CLIPBOARD CONTENT\n\n```\n{clipboard_content}\n```")
            else:
                console.print("[yellow]Warning: Clipboard is empty.[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read clipboard: {e}[/yellow]")

    # Read notes
    for note_ref in notes:
        try:
            # Parse notebook/note format
            notebook = None
            if "/" in note_ref:
                parts_split = note_ref.split("/", 1)
                notebook = parts_split[0]
                note_name = parts_split[1]
            else:
                note_name = note_ref

            path = resolve_note_ref(note_name, notebook=notebook)
            if path and path.exists():
                content = path.read_text(encoding="utf-8")
                display_name = f"{notebook}/{path.stem}" if notebook else path.stem
                parts.append(f"## NOTE: {display_name}\n\n{content}")
            else:
                console.print(f"[yellow]Warning: Note not found: {note_ref}[/yellow]")
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not read note {note_ref}: {e}[/yellow]"
            )

    return "\n\n".join(parts)


def _run_assistant_interactive(
    notebook: str | None,
    include_calendar: bool,
    use_smart: bool,
    dry_run: bool,
    token_budget: int,
    max_tools: int,
    initial_query: str | None = None,
    additional_context: str = "",
) -> None:
    """Run the interactive assistant session.

    Args:
        notebook: Focus context on specific notebook.
        include_calendar: Whether to include calendar events.
        use_smart: Use smart model vs fast model.
        dry_run: Show proposed changes without executing.
        token_budget: Maximum tokens to consume per session.
        max_tools: Maximum tool calls per turn.
        initial_query: Optional initial query to start the conversation.
        additional_context: Additional context from files, clipboard, or notes.
    """
    from nb.core.ai.assistant import (
        AssistantContext,
        clear_pending_actions,
        execute_pending_actions,
        run_assistant_turn,
    )

    context = AssistantContext()

    # Display welcome
    console.print(
        Panel.fit(
            "[bold]AI Executive Assistant[/bold]\n"
            "[dim]I can help you manage todos, search notes, and more.\n"
            "Write operations require your confirmation before executing.[/dim]",
            border_style="cyan",
        )
    )
    console.print()

    # Show what context was loaded
    if additional_context:
        console.print("[dim]Context loaded from files/clipboard/notes.[/dim]")
        console.print()

    if dry_run:
        console.print(
            "[yellow]Dry-run mode: Changes will be shown but not executed.[/yellow]"
        )
        console.print()

    console.print(
        "[dim]Commands: 'done'/'quit' to exit | 'clear' to discard pending actions[/dim]"
    )
    console.print()

    # Track if we have an initial query to process
    pending_input = initial_query

    # Interactive loop
    while True:
        # Use pending initial query or prompt for input
        if pending_input:
            user_input = pending_input
            # Display the initial query so user sees what was sent
            console.print(f"[bold green]You:[/bold green] {user_input}")
            pending_input = None  # Clear after use
        else:
            try:
                user_input = console.input("[bold green]You:[/bold green] ")
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Handle commands
        lower_input = user_input.lower()
        if lower_input in ("done", "quit", "exit", "q"):
            break

        if lower_input == "clear":
            if context.pending_actions:
                clear_pending_actions(context)
                console.print("[dim]Pending actions cleared.[/dim]")
            else:
                console.print("[dim]No pending actions.[/dim]")
            continue

        # Run assistant turn
        with console.status("[bold blue]Thinking...[/bold blue]"):
            response = run_assistant_turn(
                context=context,
                user_input=user_input,
                notebook=notebook,
                include_calendar=include_calendar,
                use_smart_model=use_smart,
                max_tool_calls=max_tools,
                token_budget=token_budget,
                additional_context=additional_context,
            )

        # Display response
        console.print()
        console.print("[bold cyan]Assistant:[/bold cyan]")
        console.print(Markdown(response))
        console.print()

        # Handle pending write actions
        if context.pending_actions:
            _display_pending_actions(context.pending_actions)

            if dry_run:
                console.print(
                    "[yellow]Dry-run: Actions shown but not executed.[/yellow]"
                )
                clear_pending_actions(context)
            else:
                # Get user confirmation
                action, indices = _get_confirmation(len(context.pending_actions))

                if action == "all":
                    # Execute all
                    results = execute_pending_actions(context)
                    _display_execution_results(results)
                elif action == "none":
                    # Discard all
                    clear_pending_actions(context)
                    console.print("[dim]Changes discarded.[/dim]")
                elif action == "select" and indices:
                    # Selective execution
                    selected_ids = [
                        context.pending_actions[i].id
                        for i in indices
                        if i < len(context.pending_actions)
                    ]
                    results = execute_pending_actions(context, action_ids=selected_ids)
                    _display_execution_results(results)
                    # Clear remaining
                    if context.pending_actions:
                        remaining = len(context.pending_actions)
                        clear_pending_actions(context)
                        console.print(f"[dim]{remaining} action(s) discarded.[/dim]")

        # Show token usage periodically
        if context.tool_calls_count > 0 and context.tool_calls_count % 5 == 0:
            console.print(
                f"[dim]Tokens: {context.input_tokens:,} in, {context.output_tokens:,} out | "
                f"Tools: {context.tool_calls_count}[/dim]"
            )

    # Final summary
    if context.executed_actions:
        console.print()
        console.print(
            f"[green]Session complete. {len(context.executed_actions)} action(s) executed.[/green]"
        )
    if context.input_tokens:
        console.print(
            f"[dim]Total tokens: {context.input_tokens:,} in, {context.output_tokens:,} out[/dim]"
        )


def _display_pending_actions(actions: list) -> None:
    """Display pending actions for confirmation."""
    console.print()
    console.print("[bold yellow]===== Proposed Changes =====[/bold yellow]")
    console.print()

    for i, action in enumerate(actions, 1):
        # Action header
        action_type_display = {
            "create_todo": "ADD TODO",
            "update_todo": "UPDATE TODO",
            "create_note": "CREATE NOTE",
            "append_to_note": "APPEND TO NOTE",
        }.get(action.action_type, action.action_type.upper())

        console.print(f"[bold][{i}] {action_type_display}[/bold]")
        console.print(f"    {action.description}")
        console.print(f"    [dim]{action.preview}[/dim]")
        console.print()

    console.print("[bold yellow]=============================[/bold yellow]")


def _get_confirmation(num_actions: int) -> tuple[str, list[int]]:
    """Get user confirmation for pending actions.

    Returns:
        Tuple of (action, indices) where:
        - action: "all", "none", or "select"
        - indices: List of 0-based indices for "select", empty otherwise
    """
    console.print()
    if num_actions == 1:
        prompt = "[bold]Apply change?[/bold] [[green]y[/green]es / [red]n[/red]o]: "
    else:
        prompt = "[bold]Apply changes?[/bold] [[green]y[/green]es / [red]n[/red]o / [cyan]1,2,3[/cyan] select]: "

    try:
        response = console.input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return ("none", [])

    if response in ("y", "yes", ""):
        return ("all", [])
    elif response in ("n", "no"):
        return ("none", [])
    else:
        # Try to parse as comma-separated numbers
        try:
            indices = []
            for part in response.replace(" ", "").split(","):
                if part.isdigit():
                    # Convert 1-based to 0-based
                    indices.append(int(part) - 1)
            if indices:
                return ("select", indices)
        except ValueError:
            pass

        console.print("[dim]Invalid input. Discarding changes.[/dim]")
        return ("none", [])


def _display_execution_results(results: list[tuple[str, bool, str]]) -> None:
    """Display results of action execution."""
    console.print()

    successes = [r for r in results if r[1]]
    failures = [r for r in results if not r[1]]

    if successes:
        console.print(
            f"[green]{len(successes)} action(s) completed successfully:[/green]"
        )
        for _action_id, _success, message in successes:
            console.print(f"  [dim]{message}[/dim]")

    if failures:
        console.print(f"[red]{len(failures)} action(s) failed:[/red]")
        for _action_id, _success, message in failures:
            console.print(f"  [red]{message}[/red]")


def register_assistant_command(cli: click.Group) -> None:
    """Register the assistant command with the CLI."""
    cli.add_command(assistant_command)
