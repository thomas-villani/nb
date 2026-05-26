"""Shell completion CLI commands and completers."""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

import click
from click.shell_completion import CompletionItem

_logger = logging.getLogger(__name__)

# Cap on how many candidates a single completion returns, so we never dump
# hundreds of entries into the shell menu.
MAX_NOTE_COMPLETIONS = 50

# Custom completion type for notebook drill-in entries (e.g. "work/"). The
# generated PowerShell script maps this to ProviderContainer so it inserts with
# no trailing space and Tab can immediately drill into the notebook. Other shells
# have no branch for this type, so they silently drop the entry (no regression --
# these positional args had no completion before).
NOTEBOOK_COMPLETION_TYPE = "namespace"


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
    except Exception as e:
        _logger.debug("Notebook completion failed: %s", e)
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
    except Exception as e:
        _logger.debug("Tag completion failed: %s", e)
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
    except Exception as e:
        _logger.debug("View completion failed: %s", e)
        return []


def _escape_like(text: str) -> str:
    """Escape SQL LIKE wildcards so user input is matched literally.

    Used with ``LIKE ? ESCAPE '\\'`` so a note ref containing % or _ does not act
    as a wildcard.
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _notes_by_path_prefix(prefix: str, limit: int) -> list[tuple[str, str]]:
    """Return (relative_path, title) for notes whose path starts with ``prefix``.

    Paths are stored relative to notes_root with forward slashes, so a prefix like
    "work" or "work/proj" naturally scopes results to that notebook. Ordered most
    recently modified first.
    """
    from nb.index.db import get_db

    db = get_db()
    pattern = _escape_like(prefix) + "%"
    rows = db.fetchall(
        "SELECT path, title FROM notes "
        "WHERE (? = '' OR path LIKE ? ESCAPE '\\') "
        "ORDER BY mtime IS NULL, mtime DESC LIMIT ?",
        (prefix, pattern, limit),
    )
    return [(row["path"], row["title"] or "") for row in rows]


def _notes_in_notebook(notebook: str, limit: int = 500) -> list[tuple[str, str]]:
    """Return (relative_path, title) for notes in ``notebook``, recent first."""
    from nb.index.db import get_db

    db = get_db()
    rows = db.fetchall(
        "SELECT path, title FROM notes WHERE notebook = ? "
        "ORDER BY mtime IS NULL, mtime DESC LIMIT ?",
        (notebook, limit),
    )
    return [(row["path"], row["title"] or "") for row in rows]


def _complete_in_notebook(notebook: str, prefix: str) -> list[CompletionItem]:
    """Complete bare note names within a notebook (when -n/--notebook is given).

    The notebook is supplied separately on the command line, so the token being
    completed is just the note name -- values are bare stems.
    """
    prefix_l = prefix.lower()
    items: list[CompletionItem] = []
    seen: set[str] = set()
    for path, title in _notes_in_notebook(notebook):
        stem = PurePosixPath(path).stem
        if stem.lower().startswith(prefix_l) and stem not in seen:
            seen.add(stem)
            items.append(CompletionItem(stem, help=title or "note"))
            if len(items) >= MAX_NOTE_COMPLETIONS:
                break
    return items


def complete_note_ref(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[CompletionItem]:
    """Complete a note reference: aliases, notebooks (drill-in), and notes.

    Tailored for PowerShell's native completer, which prefix-filters results by the
    token being typed and replaces it on accept -- so all matching here is
    prefix-based and every returned value starts with ``incomplete``. Notebook
    entries use the ``namespace`` type for clean drill-in (e.g. "work/" then Tab).

    Behavior:
    - With -n/--notebook on the command line, complete bare note names in that
      notebook.
    - Otherwise return matching aliases, notebook drill-in entries, and notes whose
      relative path matches the prefix. Because note paths are "<notebook>/<...>",
      typing a notebook name (or "<notebook>/") naturally scopes results to it.
    """
    try:
        from nb.config import get_config

        config = get_config()

        # -n/--notebook already supplies the notebook context; complete bare names.
        ctx_notebook = ctx.params.get("notebook") if ctx is not None else None
        if ctx_notebook:
            return _complete_in_notebook(ctx_notebook, incomplete)

        incomplete_l = incomplete.lower()
        items: list[CompletionItem] = []
        seen: set[str] = set()

        # 1. Aliases (highest priority) -- value round-trips via get_note_by_alias.
        from nb.core.aliases import list_note_aliases

        for alias, _path, _nb in list_note_aliases():
            if alias.lower().startswith(incomplete_l) and alias not in seen:
                seen.add(alias)
                items.append(CompletionItem(alias, help="alias"))

        # 2. Notebook drill-in entries ("work/") -- namespace type for clean drilling.
        for name in config.notebook_names():
            if name.lower().startswith(incomplete_l):
                value = f"{name}/"
                if value not in seen:
                    seen.add(value)
                    items.append(
                        CompletionItem(
                            value, type=NOTEBOOK_COMPLETION_TYPE, help="notebook"
                        )
                    )

        # 3. Notes, prefix-matched on the relative path, filling the remaining cap.
        remaining = MAX_NOTE_COMPLETIONS - len(items)
        if remaining > 0:
            for path, title in _notes_by_path_prefix(incomplete, remaining):
                value = PurePosixPath(path).with_suffix("").as_posix()
                if value not in seen:
                    seen.add(value)
                    items.append(CompletionItem(value, help=title or "note"))

        return items[:MAX_NOTE_COMPLETIONS]
    except Exception as e:
        _logger.debug("Note ref completion failed: %s", e)
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
            "namespace" { "ProviderContainer" }
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
            "namespace" { "ProviderContainer" }
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

    # The command line includes the word currently being completed as its final
    # token, but Click expects only the already-complete args (the in-progress
    # word is passed separately as `incomplete`). If we leave it in, Click treats
    # the partial token as a filled positional/option value and returns nothing.
    if word and parts and parts[-1] == word:
        parts = parts[:-1]

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
