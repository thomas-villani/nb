"""Template-related CLI commands."""

from __future__ import annotations

import click

from nb.cli.utils import console
from nb.config import get_config


def register_template_commands(cli: click.Group) -> None:
    """Register all template-related commands with the CLI."""
    cli.add_command(template)


@click.group("template", invoke_without_command=True)
@click.pass_context
def template(ctx: click.Context) -> None:
    """Manage note templates.

    Templates are stored in .nb/templates/ and can be used when
    creating new notes with 'nb new --template <name>'.

    Template variables:
      {{ date }}     - ISO date (2025-11-29)
      {{ datetime }} - ISO datetime
      {{ notebook }} - Notebook name
      {{ title }}    - Note title

    \b
    Examples:
      nb template list
      nb template new meeting
      nb template edit daily
      nb template show meeting
      nb template remove old-template
    """
    if ctx.invoked_subcommand is None:
        _list_templates()


def _list_templates() -> None:
    """List all available templates."""
    from nb.core.templates import get_template_path, list_templates

    templates = list_templates()

    if not templates:
        console.print("[dim]No templates found.[/dim]")
        console.print("[dim]Use 'nb template new <name>' to create one.[/dim]")
        return

    console.print("[bold]Available Templates[/bold]\n")
    for name in templates:
        path = get_template_path(name)
        size = path.stat().st_size
        console.print(f"  {name} [dim]({size} bytes)[/dim]")


@template.command("list")
def template_list() -> None:
    """List available templates."""
    _list_templates()


@template.command("new")
@click.argument("name")
def template_new(name: str) -> None:
    """Create a new template and open in editor.

    Creates a template file with a starter structure that you can customize.
    """
    from nb.core.templates import DEFAULT_TEMPLATE_CONTENT, create_template
    from nb.utils.editor import open_in_editor

    try:
        path = create_template(name, DEFAULT_TEMPLATE_CONTENT)
        console.print(f"[green]Created template:[/green] {name}")
        console.print(f"[dim]Location: {path}[/dim]")

        config = get_config()
        open_in_editor(path, editor=config.editor)

    except FileExistsError:
        console.print(f"[red]Template already exists:[/red] {name}")
        console.print(f"[dim]Use 'nb template edit {name}' to modify it.[/dim]")
        raise SystemExit(1) from None


@template.command("edit")
@click.argument("name")
def template_edit(name: str) -> None:
    """Open a template in the editor."""
    from nb.core.templates import get_template_path, list_templates, template_exists
    from nb.utils.editor import open_in_editor

    if not template_exists(name):
        console.print(f"[red]Template not found:[/red] {name}")
        templates = list_templates()
        if templates:
            console.print(f"[dim]Available: {', '.join(templates)}[/dim]")
        raise SystemExit(1)

    path = get_template_path(name)
    config = get_config()
    open_in_editor(path, editor=config.editor)


@template.command("show")
@click.argument("name")
def template_show(name: str) -> None:
    """Display template contents."""
    from rich.markdown import Markdown
    from rich.panel import Panel

    from nb.core.templates import read_template

    content = read_template(name)

    if content is None:
        console.print(f"[red]Template not found:[/red] {name}")
        raise SystemExit(1)

    console.print(f"\n[bold]{name}[/bold]")
    console.print(Panel(Markdown(content), border_style="dim"))


@template.command("remove")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def template_remove(name: str, yes: bool) -> None:
    """Delete a template."""
    from nb.core.templates import remove_template, template_exists

    if not template_exists(name):
        console.print(f"[red]Template not found:[/red] {name}")
        raise SystemExit(1)

    if not yes:
        if not click.confirm(f"Delete template '{name}'?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    remove_template(name)
    console.print(f"[green]Removed template:[/green] {name}")
