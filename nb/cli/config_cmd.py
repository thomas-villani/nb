"""Config-related CLI commands."""

from __future__ import annotations

from pathlib import Path

import click

from nb.cli.utils import console
from nb.config import get_config, init_config
from nb.utils.editor import open_in_editor


def register_config_commands(cli: click.Group) -> None:
    """Register all config-related commands with the CLI."""
    cli.add_command(config_cmd)


@click.group("config", invoke_without_command=True)
@click.pass_context
def config_cmd(ctx: click.Context) -> None:
    """Manage configuration settings.

    When called without a subcommand, opens the config file in the editor.

    \b
    Subcommands:
      get <key>           Get a configuration value
      set <key> <value>   Set a configuration value
      list                List all configurable settings

    \b
    Examples:
      nb config              # Open config file in editor
      nb config get editor   # Show current editor setting
      nb config set editor code  # Set editor to 'code'
      nb config list         # Show all configurable settings
    """
    if ctx.invoked_subcommand is None:
        # Default: open config file in editor
        config = get_config()

        # Ensure config exists
        if not config.config_path.exists():
            init_config(config.notes_root)

        console.print(f"[dim]Opening {config.config_path}...[/dim]")
        open_in_editor(config.config_path, editor=config.editor)


@config_cmd.command("get")
@click.argument("key")
def config_get(key: str) -> None:
    """Get a configuration value.

    \b
    Common keys:
      editor, date_format, time_format, week_start_day
      embeddings.provider, embeddings.model
      search.vector_weight, search.score_threshold
      todo.default_sort, todo.inbox_file
      clip.auto_tag_domain, clip.timeout

    \b
    Notebook-specific keys (notebook.<name>.<setting>):
      color, icon, date_based, todo_exclude, template

    \b
    Run 'nb config list' for the full set of configurable settings.
    """
    from nb.config import get_config_value

    value = get_config_value(key)
    if value is None:
        console.print(f"[red]Unknown setting:[/red] {key}")
        console.print("[dim]Use 'nb config list' to see available settings.[/dim]")
        raise SystemExit(1)

    console.print(f"{key} = {value}")


@config_cmd.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value.

    \b
    Common keys:
      editor, date_format, time_format, week_start_day
      embeddings.provider, embeddings.model
      search.vector_weight, search.score_threshold
      todo.default_sort, todo.inbox_file
      clip.auto_tag_domain, clip.timeout

    \b
    Notebook-specific keys (notebook.<name>.<setting>):
      color, icon, date_based, todo_exclude, template

    \b
    Examples:
      nb config set editor code
      nb config set notebook.work.color blue
      nb config set notebook.projects.icon wrench

    \b
    Run 'nb config list' for the full set of configurable settings.
    """
    from nb.config import set_config_value

    try:
        if set_config_value(key, value):
            console.print(f"[green]Set[/green] {key} = {value}")
        else:
            console.print(f"[red]Unknown setting:[/red] {key}")
            console.print("[dim]Use 'nb config list' to see available settings.[/dim]")
            raise SystemExit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None


@config_cmd.command("list")
def config_list() -> None:
    """List all configurable settings."""
    from nb.config import list_config_settings

    settings = list_config_settings()

    console.print("\n[bold]Configurable Settings[/bold]\n")
    for key, (description, value) in settings.items():
        value_str = str(value) if value is not None else "[dim]<not set>[/dim]"
        console.print(f"  [cyan]{key}[/cyan]")
        console.print(f"    {description}")
        console.print(f"    Current: {value_str}")
        console.print()


@config_cmd.command("edit")
def config_edit() -> None:
    """Open the config file in your editor.

    Same as running 'nb config' without a subcommand.
    """
    config = get_config()

    # Ensure config exists
    if not config.config_path.exists():
        init_config(config.notes_root)

    console.print(f"[dim]Opening {config.config_path}...[/dim]")
    open_in_editor(config.config_path, editor=config.editor)


@config_cmd.command("exclude")
@click.argument("target")
def config_exclude(target: str) -> None:
    """Exclude a notebook or note from 'nb todo'.

    TARGET can be:
    - A notebook name (e.g., 'personal') - updates config.yaml
    - A note path (e.g., 'projects/myproject.md') - updates frontmatter

    \b
    Examples:
      nb config exclude personal              # Exclude 'personal' notebook
      nb config exclude projects/myproject    # Exclude specific note
    """
    config = get_config()

    # Check if target is a notebook name
    nb_config = config.get_notebook(target)
    if nb_config:
        # Update notebook config
        if nb_config.todo_exclude:
            console.print(f"[dim]Notebook '{target}' is already excluded.[/dim]")
            return

        nb_config.todo_exclude = True
        from nb.config import save_config

        save_config(config)
        console.print(f"[green]Excluded notebook:[/green] {target}")
        return

    # Treat as a note path - update frontmatter
    note_path = Path(target)
    if not note_path.suffix:
        note_path = note_path.with_suffix(".md")

    # Try to resolve the path
    if not note_path.is_absolute():
        full_path = config.notes_root / note_path
    else:
        full_path = note_path

    if not full_path.exists():
        console.print(f"[red]Not found:[/red] {target}")
        console.print("[dim]Specify a notebook name or path to a note.[/dim]")
        raise SystemExit(1)

    # Update frontmatter
    _set_note_todo_exclude(full_path, True)
    console.print(f"[green]Excluded note:[/green] {note_path}")


@config_cmd.command("include")
@click.argument("target")
def config_include(target: str) -> None:
    """Include a notebook or note in 'nb todo'.

    TARGET can be:
    - A notebook name (e.g., 'personal') - updates config.yaml
    - A note path (e.g., 'projects/myproject.md') - updates frontmatter

    \b
    Examples:
      nb config include personal              # Include 'personal' notebook
      nb config include projects/myproject    # Include specific note
    """
    config = get_config()

    # Check if target is a notebook name
    nb_config = config.get_notebook(target)
    if nb_config:
        # Update notebook config
        if not nb_config.todo_exclude:
            console.print(f"[dim]Notebook '{target}' is already included.[/dim]")
            return

        nb_config.todo_exclude = False
        from nb.config import save_config

        save_config(config)
        console.print(f"[green]Included notebook:[/green] {target}")
        return

    # Treat as a note path - update frontmatter
    note_path = Path(target)
    if not note_path.suffix:
        note_path = note_path.with_suffix(".md")

    # Try to resolve the path
    if not note_path.is_absolute():
        full_path = config.notes_root / note_path
    else:
        full_path = note_path

    if not full_path.exists():
        console.print(f"[red]Not found:[/red] {target}")
        console.print("[dim]Specify a notebook name or path to a note.[/dim]")
        raise SystemExit(1)

    # Update frontmatter
    _set_note_todo_exclude(full_path, False)
    console.print(f"[green]Included note:[/green] {note_path}")


def _set_note_todo_exclude(path: Path, exclude: bool) -> None:
    """Set or remove todo_exclude in a note's frontmatter.

    Args:
        path: Path to the note file
        exclude: True to exclude, False to include
    """
    import frontmatter

    with path.open(encoding="utf-8") as f:
        post = frontmatter.load(f)

    if exclude:
        post.metadata["todo_exclude"] = True
    else:
        # Remove the key if it exists (False is the default)
        post.metadata.pop("todo_exclude", None)

    with path.open("w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
