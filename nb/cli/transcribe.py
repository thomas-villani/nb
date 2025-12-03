"""Transcription CLI command for nb.

Transcribes existing audio files using Deepgram.
Requires optional dependencies: uv sync --extra recorder
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
from nb.cli.completion import complete_notebook
from nb.config import get_config
from rich.console import Console

console = Console()


@click.command("transcribe")
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option("--name", "-N", help="Name for the transcript (default: filename)")
@click.option(
    "--notebook",
    "-n",
    help="Notebook to save transcript to (default: daily)",
    shell_complete=complete_notebook,
)
@click.option("--speakers", "-s", help="Speaker names (e.g., '0:Alice,1:Bob')")
@click.option("--attendees", "-a", help="Attendee list (e.g., 'Alice,Bob,Charlie')")
@click.option(
    "--copy", "copy_file", is_flag=True, help="Copy audio file to .nb/recordings/"
)
def transcribe_cmd(
        audio_file: Path,
        name: str | None,
        notebook: str | None,
        speakers: str | None,
        attendees: str | None,
        copy_file: bool,
) -> None:
    """Transcribe an audio file using Deepgram.

    AUDIO_FILE is the path to an audio file (WAV, MP3, M4A, FLAC, OGG, etc.).

    \b
    Examples:
      nb transcribe ~/Downloads/meeting.wav
      nb transcribe meeting.mp3 --name client-call
      nb transcribe recording.wav -n work --speakers "0:Me,1:Client"
      nb transcribe meeting.wav --copy   # Also copy to .nb/recordings/

    \b
    Requires:
      - uv sync --extra recorder
      - DEEPGRAM_API_KEY environment variable
    """
    from nb.recorder.formatter import (
        parse_attendees,
        parse_speaker_names,
        to_json,
        to_markdown,
    )
    from nb.recorder.transcriber import TranscriptResult, get_api_key, transcribe

    # Check API key
    if not get_api_key():
        console.print("[red]Deepgram API key not found.[/red]")
        console.print("[dim]Set DEEPGRAM_API_KEY environment variable.[/dim]")
        raise SystemExit(1)

    audio_file = Path(audio_file).resolve()
    if not audio_file.exists():
        console.print(f"[red]File not found: {audio_file}[/red]")
        raise SystemExit(1)

    config = get_config()

    # Determine recording name
    if name:
        recording_name = name
    else:
        # Use filename without extension
        recording_name = audio_file.stem

    # Add date prefix if not present
    date_str = datetime.now().strftime("%Y-%m-%d")
    if not recording_name.startswith("20"):  # Simple check for date prefix
        recording_id = f"{date_str}_{recording_name}"
    else:
        recording_id = recording_name

    console.print(f"[bold]Transcribing:[/bold] {audio_file.name}")

    # Optionally copy to recordings directory
    if copy_file:
        recordings_dir = config.nb_dir / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        dest_path = recordings_dir / f"{recording_id}{audio_file.suffix}"
        if dest_path.exists():
            console.print(
                f"[yellow]File already exists in recordings: {dest_path.name}[/yellow]"
            )
        else:
            import shutil

            shutil.copy2(audio_file, dest_path)
            console.print(f"[dim]Copied to: {dest_path.name}[/dim]")
        json_output_path = dest_path.with_suffix(".json")
    else:
        json_output_path = config.nb_dir / "recordings" / f"{recording_id}.json"
        json_output_path.parent.mkdir(parents=True, exist_ok=True)

    console.print("[cyan]Uploading to Deepgram...[/cyan]")

    try:
        result: TranscriptResult = transcribe(audio_file)
    except Exception as e:
        console.print(f"[red]Transcription failed: {e}[/red]")
        raise SystemExit(1) from e

    console.print("[cyan]Processing transcript...[/cyan]")

    # Parse speaker names and attendees
    speaker_names = parse_speaker_names(speakers)
    attendee_list = parse_attendees(attendees)

    # Save JSON
    to_json(
        result,
        json_output_path,
        source_file=audio_file.name,
        speaker_names=speaker_names,
        attendees=attendee_list,
    )
    console.print(f"[green]JSON saved:[/green] {json_output_path.name}")

    # Save Markdown to notebook
    if notebook is None:
        notebook = "daily"

    # Determine markdown output path
    from nb.core.notebooks import is_notebook_date_based

    # Generate title from name
    title_name = recording_name.replace("-", " ").replace("_", " ").title()
    title = f"Meeting: {title_name}"

    if is_notebook_date_based(notebook):
        from datetime import datetime as dt

        from nb.utils.dates import get_week_folder_name

        try:
            # Try to extract date from recording_id
            parts = recording_id.split("_", 1)
            if len(parts) == 2:
                recording_date = dt.strptime(parts[0], "%Y-%m-%d").date()
            else:
                recording_date = datetime.now().date()
        except ValueError:
            recording_date = datetime.now().date()

        # Construct path in the notebook's date structure
        nb_path = config.get_notebook_path(notebook)
        if nb_path is None:
            nb_path = config.notes_root / notebook
        year_folder = nb_path / str(recording_date.year)
        week_folder = year_folder / get_week_folder_name(recording_date)
        week_folder.mkdir(parents=True, exist_ok=True)
        md_path = week_folder / f"{recording_id}.md"
    else:
        nb_path = config.get_notebook_path(notebook)
        if nb_path is None:
            nb_path = config.notes_root / notebook
        md_path = nb_path / f"{recording_id}.md"

    # Write markdown
    to_markdown(
        result,
        md_path,
        title=title,
        speaker_names=speaker_names,
        tags=["meeting", "transcript"],
    )
    console.print(
        f"[green]Transcript saved:[/green] {md_path.relative_to(config.notes_root)}"
    )

    # Summary
    console.print()
    console.print("[bold]Transcription complete[/bold]")
    console.print(f"  Duration: {_format_duration(result.duration)}")
    console.print(f"  Speakers: {len(result.speaker_ids)}")
    console.print(f"  Utterances: {len(result.utterances)}")


def _format_duration(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def register_transcribe_commands(cli: click.Group) -> None:
    """Register transcribe command with the CLI."""
    cli.add_command(transcribe_cmd)
