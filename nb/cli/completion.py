"""Shell completion CLI commands."""

from __future__ import annotations

import click


def register_completion_commands(cli: click.Group) -> None:
    """Register all completion-related commands with the CLI."""
    cli.add_command(completion_cmd)


def _get_powershell_source() -> str:
    """Generate PowerShell completion script for nb."""
    return """\
Register-ArgumentCompleter -Native -CommandName nb -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $env:_NB_COMPLETE = "powershell_complete"
    $env:_NB_COMPLETE_ARGS = $commandAst.ToString()
    $env:_NB_COMPLETE_WORD = $wordToComplete
    nb | ForEach-Object {
        $type, $value, $help = $_ -split "`t", 3
        [System.Management.Automation.CompletionResult]::new(
            $value,
            $value,
            $(if ($type -eq "dir") { "ParameterValue" } elseif ($type -eq "file") { "ParameterValue" } else { "ParameterValue" }),
            $(if ($help) { $help } else { $value })
        )
    }
    Remove-Item Env:_NB_COMPLETE
    Remove-Item Env:_NB_COMPLETE_ARGS
    Remove-Item Env:_NB_COMPLETE_WORD
}
"""


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
