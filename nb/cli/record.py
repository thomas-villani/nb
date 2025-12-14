"""Recording CLI commands for nb.

Provides audio recording and transcription functionality.
Requires optional dependencies: uv sync --extra recorder
"""

from __future__ import annotations

import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console

from nb.cli.completion import complete_notebook
from nb.config import get_config

console = Console()


def _check_recorder_available() -> bool:
    """Check if recorder dependencies are installed, show helpful message if not."""
    try:
        from nb.recorder import is_available

        if not is_available():
            console.print(
                "[red]Recording features require additional dependencies.[/red]"
            )
            console.print("[dim]Install with: uv sync --extra recorder[/dim]")
            return False
        return True
    except ImportError:
        console.print("[red]Recording module not found.[/red]")
        return False


@click.group("record")
def record_group() -> None:
    """Record meetings and transcribe audio.

    Captures audio from your microphone and system (meeting participants),
    then transcribes using Deepgram with speaker diarization.

    \b
    Quick start:
      nb record start              # Start recording (Ctrl+C to stop)
      nb record start --name call  # Name the recording
      nb record start --mic-only   # Record microphone only
      nb record list               # List recordings
      nb record transcribe <id>    # Re-transcribe a recording
      nb record purge              # Delete old audio files

    \b
    To transcribe an existing audio file, use:
      nb transcribe meeting.wav

    \b
    Requires: uv sync --extra recorder
    """
    pass


@record_group.command("start")
@click.option("--name", "-N", default="recording", help="Name for the recording")
@click.option(
    "--notebook",
    "-n",
    help="Notebook to save transcript to (default: daily)",
    shell_complete=complete_notebook,
)
@click.option(
    "--audio-only", is_flag=True, help="Skip transcription, only record audio"
)
@click.option(
    "--delete-audio",
    "-x",
    is_flag=True,
    help="Delete WAV file after successful transcription",
)
@click.option(
    "--mic-only", "-mo", is_flag=True, help="Record microphone only (no system audio)"
)
@click.option(
    "--system-only",
    "-so",
    is_flag=True,
    help="Record system audio only (no microphone)",
)
@click.option(
    "--dictate",
    "-d",
    is_flag=True,
    help="Dictation mode: mic-only with optimized transcription",
)
@click.option("--mic", "-m", type=int, help="Microphone device index")
@click.option("--loopback", "-l", type=int, help="System audio (loopback) device index")
def record_start(
    name: str,
    notebook: str | None,
    audio_only: bool,
    delete_audio: bool,
    mic_only: bool,
    system_only: bool,
    dictate: bool,
    mic: int | None,
    loopback: int | None,
) -> None:
    """Start recording audio.

    Records until you press Ctrl+C. By default, transcribes automatically
    after recording stops.

    \b
    Examples:
      nb record start                     # Record mic + system audio
      nb record start --name standup      # Named recording
      nb record start -n work             # Save transcript to 'work' notebook
      nb record start --audio-only        # Record without transcription
      nb record start --mic-only          # Microphone only
      nb record start --system-only       # System audio only
      nb record start --delete-audio      # Delete WAV after transcription
      nb record start --mic 1 --loopback 3  # Specify devices

    \b
    Audio channels:
      - Both (default): Stereo WAV (left=mic, right=system)
      - Mic only: Mono WAV
      - System only: Stereo or mono WAV
    """
    if not _check_recorder_available():
        raise SystemExit(1)

    # Dictate mode implies mic-only
    if dictate:
        mic_only = True

    if mic_only and system_only:
        console.print("[red]Cannot use both --mic-only and --system-only[/red]")
        raise SystemExit(1)

    from nb.recorder.audio import (
        RecordingMode,
        get_recording_path,
        start_recording,
        stop_recording,
    )

    config = get_config()

    # Determine recording mode
    if mic_only:
        mode = RecordingMode.MIC_ONLY
    elif system_only:
        mode = RecordingMode.SYSTEM_ONLY
    else:
        mode = RecordingMode.BOTH

    # Use config defaults if not specified on command line
    if mic is None and config.recorder.mic_device is not None:
        mic = config.recorder.mic_device
    if loopback is None and config.recorder.loopback_device is not None:
        loopback = config.recorder.loopback_device

    # Check config for auto_delete_audio
    if not delete_audio and config.recorder.auto_delete_audio:
        delete_audio = True

    # Determine recordings directory
    recordings_dir = config.nb_dir / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)

    # Generate output path
    output_path = get_recording_path(name, recordings_dir)

    # Check if file already exists
    if output_path.exists():
        console.print(f"[yellow]Recording already exists: {output_path.name}[/yellow]")
        console.print(
            "[dim]Use a different --name or delete the existing recording.[/dim]"
        )
        raise SystemExit(1)

    # Start recording
    try:
        session = start_recording(
            output_path=output_path,
            mic_device=mic,
            loopback_device=loopback,
            sample_rate=config.recorder.sample_rate,
            mode=mode,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        console.print("[dim]Run 'nb record devices' to list available devices.[/dim]")
        raise SystemExit(1) from e
    except Exception as e:
        console.print(f"[red]Failed to start recording: {e}[/red]")
        raise SystemExit(1) from e

    # Wait for recording to actually start
    if not session.wait_for_start(timeout=5.0):
        console.print("[red]Recording failed to start within timeout[/red]")
        raise SystemExit(1)

    # Check for early errors
    if session._error:
        console.print(f"[red]Recording failed: {session._error}[/red]")
        raise SystemExit(1)

    mode_str = {
        RecordingMode.BOTH: "mic + system",
        RecordingMode.MIC_ONLY: "mic only",
        RecordingMode.SYSTEM_ONLY: "system only",
    }[mode]

    console.print(f"[green]Recording started:[/green] {name}")
    console.print(f"    Mode: {mode_str}")
    console.print(f"    Output: {output_path.name}")
    console.print("    [dim]Press Ctrl+C to stop...[/dim]")
    console.print()

    # Use Rich Progress with spinner and elapsed time
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    stop_requested = False
    final_duration = 0.0

    # Handle Ctrl+C gracefully
    def signal_handler(sig: int, frame: object) -> None:
        nonlocal stop_requested, final_duration
        stop_requested = True
        final_duration = session.duration

    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal_handler)

    # Wait for recording with spinner + elapsed time
    import time

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            _task = progress.add_task("Recording", total=None)
            while session.is_recording and not stop_requested:
                time.sleep(0.25)
                # Check for errors
                if session._error:
                    progress.stop()
                    console.print(f"[red]Recording error: {session._error}[/red]")
                    raise SystemExit(1)
    except KeyboardInterrupt:
        stop_requested = True
        final_duration = session.duration

    # Handle stop
    if stop_requested or not session.is_recording:
        console.print("[yellow]Stopping recording...[/yellow]")
        try:
            result_path = stop_recording(session)
            duration_str = _format_duration(
                final_duration if final_duration > 0 else session.duration
            )
            console.print(
                f"[green]Recording saved:[/green] {result_path.name} ({duration_str})"
            )

            # Auto-transcribe unless --audio-only
            if not audio_only:
                _transcribe_recording(
                    result_path,
                    notebook=notebook,
                    delete_audio=delete_audio,
                    dictation=dictate,
                )
            elif delete_audio:
                console.print(
                    "[yellow]--delete-audio ignored with --audio-only[/yellow]"
                )

        except Exception as e:
            console.print(f"[red]Error stopping recording: {e}[/red]")
            raise SystemExit(1) from e

        raise SystemExit(0)

    # If we get here, recording stopped unexpectedly
    if session._error:
        console.print(f"[red]Recording stopped unexpectedly: {session._error}[/red]")
        raise SystemExit(1)


@record_group.command("stop")
def record_stop() -> None:
    """Stop the active recording.

    Note: Usually you'll just press Ctrl+C in the 'start' command.
    This command is for stopping a recording started in the background.
    """
    console.print("[yellow]No background recording support yet.[/yellow]")
    console.print("[dim]Use Ctrl+C in the 'nb record start' terminal.[/dim]")


@record_group.command("transcribe")
@click.argument("recording_id", required=False)
@click.option(
    "--notebook",
    "-n",
    help="Notebook to save transcript to",
    shell_complete=complete_notebook,
)
@click.option("--speakers", "-s", help="Speaker names (e.g., '0:Alice,1:Bob')")
@click.option("--attendees", "-a", help="Attendee list (e.g., 'Alice,Bob,Charlie')")
@click.option(
    "--all", "transcribe_all", is_flag=True, help="Transcribe all pending recordings"
)
@click.option(
    "--delete-audio",
    is_flag=True,
    help="Delete WAV file after successful transcription",
)
def record_transcribe(
    recording_id: str | None,
    notebook: str | None,
    speakers: str | None,
    attendees: str | None,
    transcribe_all: bool,
    delete_audio: bool,
) -> None:
    """Transcribe a recording using Deepgram.

    RECORDING_ID is the recording name (e.g., "2025-12-01_standup").
    Omit the .wav extension.

    \b
    Examples:
      nb record transcribe 2025-12-01_standup
      nb record transcribe 2025-12-01_standup --speakers "0:Me,1:Client"
      nb record transcribe --all              # Transcribe all pending
      nb record transcribe --all --delete-audio  # Transcribe and clean up

    \b
    Output files:
      - .nb/recordings/<id>.json   (structured data)
      - <notebook>/<date>_<name>.md (human-readable, indexed by nb)
    """
    if not _check_recorder_available():
        raise SystemExit(1)

    config = get_config()
    recordings_dir = config.nb_dir / "recordings"

    # Check config for auto_delete_audio
    if not delete_audio and config.recorder.auto_delete_audio:
        delete_audio = True

    if transcribe_all:
        # Find all WAV files without corresponding JSON
        pending = _get_pending_recordings(recordings_dir)
        if not pending:
            console.print("[dim]No pending recordings to transcribe.[/dim]")
            return

        console.print(f"[bold]Transcribing {len(pending)} recording(s)...[/bold]")
        for wav_path in pending:
            console.print(f"\n[cyan]{wav_path.stem}[/cyan]")
            _transcribe_recording(
                wav_path,
                notebook=notebook,
                speakers=speakers,
                attendees=attendees,
                delete_audio=delete_audio,
            )
        return

    if not recording_id:
        # Show recent recordings
        recordings = list(recordings_dir.glob("*.wav"))
        if not recordings:
            console.print("[dim]No recordings found.[/dim]")
            console.print("[dim]Start a recording with: nb record start[/dim]")
            return

        console.print("[bold]Recent recordings:[/bold]")
        for wav in sorted(recordings, key=lambda p: p.stat().st_mtime, reverse=True)[
            :10
        ]:
            json_exists = wav.with_suffix(".json").exists()
            status = (
                "[green]transcribed[/green]"
                if json_exists
                else "[yellow]pending[/yellow]"
            )
            console.print(f"  {wav.stem}  {status}")
        console.print("\n[dim]Usage: nb record transcribe <recording_id>[/dim]")
        return

    # Find the recording
    wav_path = recordings_dir / f"{recording_id}.wav"
    if not wav_path.exists():
        # Try without date prefix
        matches = list(recordings_dir.glob(f"*_{recording_id}.wav"))
        if matches:
            wav_path = matches[0]
        else:
            console.print(f"[red]Recording not found: {recording_id}[/red]")
            console.print(
                "[dim]Run 'nb record list' to see available recordings.[/dim]"
            )
            raise SystemExit(1)

    _transcribe_recording(
        wav_path,
        notebook=notebook,
        speakers=speakers,
        attendees=attendees,
        delete_audio=delete_audio,
    )


@record_group.command("list")
@click.option(
    "--status", type=click.Choice(["pending", "transcribed", "all"]), default="all"
)
def record_list(status: str) -> None:
    """List recordings.

    \b
    Examples:
      nb record list                 # All recordings
      nb record list --status pending    # Only untranscribed
      nb record list --status transcribed  # Only transcribed
    """
    config = get_config()
    recordings_dir = config.nb_dir / "recordings"

    if not recordings_dir.exists():
        console.print("[dim]No recordings directory found.[/dim]")
        console.print("[dim]Start a recording with: nb record start[/dim]")
        return

    recordings = list(recordings_dir.glob("*.wav"))
    if not recordings:
        console.print("[dim]No recordings found.[/dim]")
        return

    # Sort by modification time, newest first
    recordings.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    console.print("[bold]Recordings[/bold]\n")

    for wav in recordings:
        json_exists = wav.with_suffix(".json").exists()

        # Filter by status
        if status == "pending" and json_exists:
            continue
        if status == "transcribed" and not json_exists:
            continue

        # Get file info
        stat = wav.stat()
        size_mb = stat.st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(stat.st_mtime)

        status_str = (
            "[green]transcribed[/green]" if json_exists else "[yellow]pending[/yellow]"
        )
        console.print(f"  {wav.stem}")
        console.print(
            f"    {status_str}  {size_mb:.1f} MB  {modified.strftime('%Y-%m-%d %H:%M')}"
        )


@record_group.command("purge")
@click.option(
    "--transcribed", is_flag=True, help="Delete only transcribed recordings (have JSON)"
)
@click.option(
    "--all", "purge_all", is_flag=True, help="Delete all recordings (including pending)"
)
@click.option("--older-than", type=int, help="Delete recordings older than N days")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be deleted without deleting"
)
@click.confirmation_option(prompt="Are you sure you want to delete recordings?")
def record_purge(
    transcribed: bool,
    purge_all: bool,
    older_than: int | None,
    dry_run: bool,
) -> None:
    """Delete old audio recordings to free up space.

    By default, deletes only transcribed recordings (those with a .json file).
    The JSON transcript files are preserved.

    \b
    Examples:
      nb record purge                    # Delete transcribed WAV files
      nb record purge --older-than 30    # Delete transcribed older than 30 days
      nb record purge --all              # Delete all WAV files (including pending)
      nb record purge --dry-run          # Show what would be deleted
    """
    config = get_config()
    recordings_dir = config.nb_dir / "recordings"

    if not recordings_dir.exists():
        console.print("[dim]No recordings directory found.[/dim]")
        return

    recordings = list(recordings_dir.glob("*.wav"))
    if not recordings:
        console.print("[dim]No recordings to purge.[/dim]")
        return

    # Filter recordings
    to_delete: list[Path] = []
    now = datetime.now()

    for wav in recordings:
        json_exists = wav.with_suffix(".json").exists()

        # By default, only delete transcribed recordings
        if not purge_all and not json_exists:
            continue

        # If --transcribed flag, only delete transcribed
        if transcribed and not json_exists:
            continue

        # Check age filter
        if older_than is not None:
            modified = datetime.fromtimestamp(wav.stat().st_mtime)
            age_days = (now - modified).days
            if age_days < older_than:
                continue

        to_delete.append(wav)

    if not to_delete:
        console.print("[dim]No recordings match the criteria.[/dim]")
        return

    # Calculate total size
    total_size = sum(f.stat().st_size for f in to_delete)
    size_mb = total_size / (1024 * 1024)

    if dry_run:
        console.print(
            f"[bold]Would delete {len(to_delete)} recording(s) ({size_mb:.1f} MB):[/bold]"
        )
        for wav in sorted(to_delete, key=lambda p: p.stat().st_mtime):
            console.print(f"  {wav.name}")
        return

    # Delete files
    for wav in to_delete:
        wav.unlink()

    console.print(
        f"[green]Deleted {len(to_delete)} recording(s) ({size_mb:.1f} MB)[/green]"
    )


@record_group.command("devices")
def record_devices() -> None:
    """List available audio devices.

    Shows input devices (microphones) and output devices that can be
    used for system audio loopback.

    Use the device index with --mic and --loopback options in 'nb record start',
    or configure defaults in config.yaml under 'recorder'.
    """
    if not _check_recorder_available():
        raise SystemExit(1)

    from nb.recorder.audio import get_wasapi_devices, list_devices

    config = get_config()
    devices = list_devices()
    _, outputs = get_wasapi_devices()

    console.print("[bold]Input Devices (Microphones / System Audio)[/bold]\n")
    input_devices = [d for d in devices if d.is_input]
    if input_devices:
        for dev in input_devices:
            api_tag = (
                f" [dim]({dev.hostapi_name})[/dim]"
                if "WASAPI" not in dev.hostapi_name
                else ""
            )
            # Show configured status for both mic and loopback (Stereo Mix can be loopback)
            tags = []
            if dev.index == config.recorder.mic_device:
                tags.append("[cyan](mic)[/cyan]")
            if dev.index == config.recorder.loopback_device:
                tags.append("[green](system audio)[/green]")
            configured = " " + " ".join(tags) if tags else ""
            console.print(f"  [{dev.index}] {dev.name}{api_tag}{configured}")
    else:
        console.print("  [dim]No input devices found[/dim]")

    console.print("\n[bold]Output Devices (for Loopback)[/bold]\n")
    if outputs:
        for dev in outputs:
            configured = (
                " [cyan](configured)[/cyan]"
                if dev.index == config.recorder.loopback_device
                else ""
            )
            console.print(f"  [{dev.index}] {dev.name}{configured}")
        console.print(
            "\n  [dim]Note: WASAPI loopback captures system audio from these devices.[/dim]"
        )
    else:
        console.print("  [dim]No WASAPI output devices found[/dim]")
        console.print("  [dim]System audio capture may not be available.[/dim]")

    console.print(
        "\n[dim]Configure defaults: nb config set recorder.mic_device <index>[/dim]"
    )


def _format_duration(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _get_pending_recordings(recordings_dir: Path) -> list[Path]:
    """Get recordings that haven't been transcribed yet."""
    if not recordings_dir.exists():
        return []

    pending = []
    for wav in recordings_dir.glob("*.wav"):
        if not wav.with_suffix(".json").exists():
            pending.append(wav)

    return sorted(pending, key=lambda p: p.stat().st_mtime)


def _process_dictation_text(text: str) -> str:
    """Post-process dictation text to convert spoken commands.

    Converts phrases like "new todo item:" to checkbox format "- [ ]".
    """
    import re

    # Patterns for creating todo items (case-insensitive)
    todo_patterns = [
        (r"(?i)\bnew todo item[:\s]+", "- [ ] "),
        (r"(?i)\bnew todo[:\s]+", "- [ ] "),
        (r"(?i)\btodo item[:\s]+", "- [ ] "),
        (r"(?i)\badd todo[:\s]+", "- [ ] "),
        (r"(?i)\bnew task[:\s]+", "- [ ] "),
    ]

    for pattern, replacement in todo_patterns:
        text = re.sub(pattern, replacement, text)

    return text


def _transcribe_recording(
    wav_path: Path,
    notebook: str | None = None,
    speakers: str | None = None,
    attendees: str | None = None,
    delete_audio: bool = False,
    dictation: bool = False,
) -> None:
    """Transcribe a recording and save outputs."""
    from nb.recorder.formatter import (
        parse_attendees,
        parse_speaker_names,
        to_json,
        to_markdown,
    )
    from nb.recorder.transcriber import TranscriptResult, get_api_key, transcribe

    # Get config for paths and settings
    config = get_config()

    # Check API key
    if not get_api_key():
        console.print("[red]Deepgram API key not found.[/red]")
        console.print("[dim]Set DEEPGRAM_API_KEY environment variable.[/dim]")
        raise SystemExit(1)

    start_time = time.time()
    console.print("[cyan]Uploading to Deepgram...[/cyan]")

    try:
        result: TranscriptResult = transcribe(
            wav_path,
            dictation=dictation,
            timeout=config.recorder.transcribe_timeout,
        )
    except Exception as e:
        console.print(f"[red]Transcription failed: {e}[/red]")
        raise SystemExit(1) from e

    finish_time = time.time() - start_time
    console.print(f"[cyan]Finished transcription ({finish_time / 60:.2f} min.)[/cyan]")

    # Post-process dictation transcripts
    if dictation:
        for utterance in result.utterances:
            utterance.text = _process_dictation_text(utterance.text)

    console.print("[cyan]Processing transcript...[/cyan]")

    # Parse speaker names and attendees
    speaker_names = parse_speaker_names(speakers)
    attendee_list = parse_attendees(attendees)

    # Save JSON to recordings dir
    json_path = wav_path.with_suffix(".json")
    to_json(
        result,
        json_path,
        source_file=wav_path.name,
        speaker_names=speaker_names,
        attendees=attendee_list,
    )
    console.print(f"[green]JSON saved:[/green] {json_path.name}")

    # Save Markdown to notebook
    if notebook is None:
        from nb.core.notebooks import get_default_transcript_notebook

        notebook = get_default_transcript_notebook()

    # Determine markdown output path
    from nb.core.notebooks import is_notebook_date_based

    # Extract date and name from recording ID (e.g., "2025-12-01_1430_standup")
    recording_id = wav_path.stem
    parts = recording_id.split("_", 2)  # date_time_name
    if len(parts) >= 2:
        date_str = parts[0]
        name = parts[-1] if len(parts) > 2 else parts[1]
        if dictation:
            title = f"Voice Note: {name.replace('-', ' ').replace('_', ' ').title()}"
        else:
            title = f"Meeting: {name.replace('-', ' ').replace('_', ' ').title()}"
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        name = recording_id
        title = "Voice Note" if dictation else f"Meeting: {name}"

    # Create note in the target notebook
    if is_notebook_date_based(notebook):
        # For date-based notebooks, use the recording date
        from datetime import datetime as dt

        from nb.utils.dates import get_week_folder_name

        try:
            recording_date = dt.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            recording_date = dt.now().date()

        # Construct path in the notebook's date structure
        nb_path = config.get_notebook_path(notebook)
        if nb_path is None:
            nb_path = config.notes_root / notebook
        year_folder = nb_path / str(recording_date.year)
        week_folder = year_folder / get_week_folder_name(recording_date)
        week_folder.mkdir(parents=True, exist_ok=True)
        md_path = week_folder / f"{recording_id}.md"
    else:
        # For non-date-based notebooks, just put in root
        nb_path = config.get_notebook_path(notebook)
        if nb_path is None:
            nb_path = config.notes_root / notebook
        md_path = nb_path / f"{recording_id}.md"

    # Write markdown
    tags = ["voice-note", "dictation"] if dictation else ["meeting", "transcript"]
    to_markdown(
        result,
        md_path,
        title=title,
        speaker_names=speaker_names,
        tags=tags,
    )
    console.print(
        f"[green]Transcript saved:[/green] {md_path.relative_to(config.notes_root)}"
    )

    # Delete audio file if requested
    if delete_audio:
        wav_path.unlink()
        console.print(f"[dim]Audio file deleted: {wav_path.name}[/dim]")

    # Summary
    console.print()
    console.print("[bold]Transcription complete[/bold]")
    console.print(f"  Duration: {_format_duration(result.duration)}")
    console.print(f"  Speakers: {len(result.speaker_ids)}")
    console.print(f"  Utterances: {len(result.utterances)}")


def register_record_commands(cli: click.Group) -> None:
    """Register recording commands with the CLI."""
    cli.add_command(record_group)
