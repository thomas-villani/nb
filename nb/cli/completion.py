"""Shell completion CLI commands and completers."""

from __future__ import annotations

import click
from click.shell_completion import CompletionItem


def register_completion_commands(cli: click.Group) -> None:
    """Register all completion-related commands with the CLI."""
    cli.add_command(completion_cmd)


# =============================================================================
# Custom Completers
# =============================================================================


def complete_notebook(
        ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[CompletionItem]:
    """Complete notebook names from configuration."""
    try:
        from nb.config import get_config

        config = get_config()
        names = config.notebook_names()
        return [
            CompletionItem(name, help="notebook")
            for name in names
            if name.startswith(incomplete)
        ]
    except Exception:
        return []


def complete_tag(
        ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[CompletionItem]:
    """Complete tag names from indexed todos."""
    try:
        from nb.index.todos_repo import get_tag_stats

        stats = get_tag_stats()
        return [
            CompletionItem(t["tag"], help=f"{t['count']} todos")
            for t in stats
            if t["tag"].startswith(incomplete)
        ]
    except Exception:
        return []


def complete_view(
        ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[CompletionItem]:
    """Complete saved todo view names."""
    try:
        from nb.config import get_config

        config = get_config()
        names = config.todo_view_names()
        return [
            CompletionItem(name, help="saved view")
            for name in names
            if name.startswith(incomplete)
        ]
    except Exception:
        return []


def _get_powershell_source(include_nbt: bool = True) -> str:
    """Generate PowerShell completion script for nb (and optionally nbt)."""
    nb_script = """\
Register-ArgumentCompleter -Native -CommandName nb -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $env:_NB_COMPLETE = "powershell_complete"
    $env:_NB_COMPLETE_ARGS = $commandAst.ToString()
    $env:_NB_COMPLETE_WORD = $wordToComplete
    nb | ForEach-Object {
        $type, $value, $help = $_ -split "`t", 3
        $resultType = switch ($type) {
            "dir"  { "ProviderContainer" }
            "file" { "ProviderItem" }
            default { "ParameterValue" }
        }
        [System.Management.Automation.CompletionResult]::new(
            $value,
            $value,
            $resultType,
            $(if ($help) { $help } else { $value })
        )
    }
    Remove-Item Env:_NB_COMPLETE
    Remove-Item Env:_NB_COMPLETE_ARGS
    Remove-Item Env:_NB_COMPLETE_WORD
}
"""
    if not include_nbt:
        return nb_script

    # nbt is an alias for "nb todo", so we prepend "nb todo" to the args
    nbt_script = """
Register-ArgumentCompleter -Native -CommandName nbt -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $env:_NB_COMPLETE = "powershell_complete"
    # Prepend "nb todo" to simulate nbt -> nb todo
    $nbtArgs = $commandAst.ToString()
    $nbtArgs = $nbtArgs -replace "^nbt", "nb todo"
    $env:_NB_COMPLETE_ARGS = $nbtArgs
    $env:_NB_COMPLETE_WORD = $wordToComplete
    nb | ForEach-Object {
        $type, $value, $help = $_ -split "`t", 3
        $resultType = switch ($type) {
            "dir"  { "ProviderContainer" }
            "file" { "ProviderItem" }
            default { "ParameterValue" }
        }
        [System.Management.Automation.CompletionResult]::new(
            $value,
            $value,
            $resultType,
            $(if ($help) { $help } else { $value })
        )
    }
    Remove-Item Env:_NB_COMPLETE
    Remove-Item Env:_NB_COMPLETE_ARGS
    Remove-Item Env:_NB_COMPLETE_WORD
}
"""
    return nb_script + nbt_script


def handle_powershell_completion(cli: click.Group) -> bool:
    """Handle PowerShell completion if requested via env var. Returns True if handled."""
    import os
    import shlex

    complete_var = os.environ.get("_NB_COMPLETE")
    if complete_var != "powershell_complete":
        return False

    args_str = os.environ.get("_NB_COMPLETE_ARGS", "")
    word = os.environ.get("_NB_COMPLETE_WORD", "")

    # Parse the command line
    try:
        # Remove the 'nb' command name
        parts = shlex.split(args_str)
        if parts and parts[0] == "nb":
            parts = parts[1:]
    except ValueError:
        parts = []

    # Use click's completion mechanism
    from click.shell_completion import ShellComplete

    comp = ShellComplete(cli, {}, "nb", "_NB_COMPLETE")
    completions = comp.get_completions(parts, word)

    for item in completions:
        # Output format: type\tvalue\thelp
        help_text = item.help or ""
        click.echo(f"{item.type}\t{item.value}\t{help_text}")

    return True


@click.command("completion")
@click.option(
    "--shell",
    "-s",
    type=click.Choice(["powershell", "bash", "zsh", "fish"]),
    default="powershell",
    help="Shell to generate completion for",
)
@click.pass_context
def completion_cmd(ctx: click.Context, shell: str) -> None:
    """Generate shell completion script.

    Generates completion scripts for both 'nb' and 'nbt' commands.

    \b
    For PowerShell, add this to your $PROFILE:
        nb completion | Out-String | Invoke-Expression

    \b
    Or save to a file and source it:
        nb completion > ~/.nb-completion.ps1
        . ~/.nb-completion.ps1

    \b
    For Bash, add to ~/.bashrc:
        eval "$(nb completion -s bash)"

    \b
    For Zsh, add to ~/.zshrc:
        eval "$(nb completion -s zsh)"

    \b
    For Fish, add to ~/.config/fish/completions/nb.fish:
        nb completion -s fish > ~/.config/fish/completions/nb.fish
    """
    import click.shell_completion as shell_completion

    # Get the root CLI from context
    root_cli = ctx.find_root().command

    if shell == "powershell":
        click.echo(_get_powershell_source())
    else:
        shell_map = {
            "bash": shell_completion.BashComplete,
            "zsh": shell_completion.ZshComplete,
            "fish": shell_completion.FishComplete,
        }
        cls = shell_map[shell]
        comp = cls(root_cli, {}, "nb", "_NB_COMPLETE")
        click.echo(comp.source())
