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
from typing import TYPE_CHECKING

import click
from rich.console import Console

from nb.cli.completion import complete_notebook
from nb.config import get_config

if TYPE_CHECKING:
    from nb.recorder.audio import RecordingSession
    from nb.recorder.transcriber import TranscriptResult

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
    then transcribes using Deepgram with speaker diarization. Recordings
    auto-stop after a configurable duration (default 30 min) and can be
    extended on the fly. An interactive widget lets you type notes during
    the recording, and an LLM can generate meeting notes from the transcript.

    \b
    Quick start:
      nb record start                    # Record with 30-min auto-stop
      nb record start --name standup     # Name the recording
      nb record start -t 60             # Record up to 60 minutes
      nb record start -t 0              # No auto-stop
      nb record start --no-summarize    # Skip LLM meeting notes
      nb record start --mic-only        # Record microphone only
      nb record list                    # List recordings
      nb record transcribe <id>         # Re-transcribe a recording
      nb record recover [<id>]          # Rebuild a note from an existing transcript
      nb record purge                   # Delete old audio files

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
@click.option(
    "--duration",
    "-t",
    type=int,
    default=30,
    show_default=True,
    help="Auto-stop after N minutes (0 for no limit)",
)
@click.option(
    "--summarize/--no-summarize",
    default=True,
    show_default=True,
    help="Generate meeting notes from transcript using LLM",
)
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
    duration: int,
    summarize: bool,
) -> None:
    """Start recording audio.

    Records with an interactive widget showing elapsed time, remaining time,
    and a notes textarea. Auto-stops after --duration minutes (default 30).
    Use the +5/+10 min buttons to extend if needed. Notes typed during
    recording are included in the transcript.

    \b
    Examples:
      nb record start                     # Record with 30-min auto-stop
      nb record start --name standup      # Named recording
      nb record start -t 60              # Record up to 60 minutes
      nb record start -t 0               # No auto-stop (Ctrl+C to stop)
      nb record start -n work             # Save transcript to 'work' notebook
      nb record start --no-summarize      # Skip LLM meeting notes
      nb record start --audio-only        # Record without transcription
      nb record start --mic-only          # Microphone only
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

    # Calculate timeout in seconds (0 means no timeout)
    timeout_seconds = duration * 60 if duration > 0 else None

    console.print(f"[green]Recording started:[/green] {name}")
    console.print(f"    Mode: {mode_str}")
    if mode in (RecordingMode.BOTH, RecordingMode.SYSTEM_ONLY):
        if session.loopback_method == "wasapi-loopback":
            console.print(
                f"    System audio: {session.loopback_name} [dim](WASAPI loopback)[/dim]"
            )
        elif session.loopback_method == "stereo-mix":
            console.print(
                f"    System audio: {session.loopback_name} [dim](Stereo Mix)[/dim]"
            )
            console.print(
                "    [yellow]Warning:[/yellow] Stereo Mix only captures the onboard "
                "audio chip. If playback is on headphones or a USB/Bluetooth device, "
                "participants will not be recorded."
            )
        else:
            console.print(
                "    [red]System audio: NOT being captured[/red] "
                "[dim](other participants will be missing)[/dim]"
            )
    console.print(f"    Output: {output_path.name}")
    if timeout_seconds:
        console.print(f"    Auto-stop: {duration} min")
    console.print()

    # Try to use interactive Wijjit widget, fall back to simple spinner
    user_notes = ""
    try:
        from nb.tui.recording import run_recording_widget

        user_notes = run_recording_widget(
            session=session,
            name=name,
            mode_str=mode_str,
            timeout_seconds=timeout_seconds,
        )
    except ImportError:
        # Wijjit not available — fall back to simple spinner
        user_notes = _recording_spinner_fallback(session, timeout_seconds)

    # Stop recording
    final_duration = session.duration
    console.print("[yellow]Stopping recording...[/yellow]")
    try:
        result_path = stop_recording(session)
        duration_str = _format_duration(final_duration)
        console.print(
            f"[green]Recording saved:[/green] {result_path.name} ({duration_str})"
        )
        _report_levels(session, mode)

        # Auto-transcribe unless --audio-only
        if not audio_only:
            _transcribe_recording(
                result_path,
                notebook=notebook,
                delete_audio=delete_audio,
                dictation=dictate,
                user_notes=user_notes,
                summarize=summarize,
            )
        elif delete_audio:
            console.print("[yellow]--delete-audio ignored with --audio-only[/yellow]")

    except Exception as e:
        console.print(f"[red]Error stopping recording: {e}[/red]")
        raise SystemExit(1) from e

    raise SystemExit(0)


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


@record_group.command("recover")
@click.argument("recording_id", required=False)
@click.option(
    "--notebook",
    "-n",
    help="Notebook to save the note to (default: daily)",
    shell_complete=complete_notebook,
)
@click.option(
    "--speakers",
    "-s",
    help="Override speaker names (e.g., '0:Alice,1:Bob'); defaults to labels in the JSON",
)
@click.option(
    "--summarize/--no-summarize",
    default=True,
    show_default=True,
    help="Generate meeting notes from transcript using LLM",
)
@click.option(
    "--dictation",
    "-d",
    is_flag=True,
    help="Treat as a voice note (dictation) rather than a meeting",
)
@click.option(
    "--force", "-f", is_flag=True, help="Overwrite the note if it already exists"
)
def record_recover(
    recording_id: str | None,
    notebook: str | None,
    speakers: str | None,
    summarize: bool,
    dictation: bool,
    force: bool,
) -> None:
    """Rebuild a note from an existing transcript JSON (no re-transcription).

    Use this when a recording was transcribed (a .json exists in
    .nb/recordings/) but the markdown note was never written — e.g. the machine
    shut down before the note was saved. Unlike `nb record transcribe`, this
    does NOT call Deepgram or need the .wav file; it rebuilds the note straight
    from the saved transcript.

    With no RECORDING_ID, lists transcripts whose note appears to be missing.

    \b
    Examples:
      nb record recover                        # List transcripts with no note
      nb record recover 2026-06-15_1003_hcanj  # Rebuild that note
      nb record recover <id> -n work           # Save to a specific notebook
      nb record recover <id> --no-summarize    # Skip LLM meeting notes
      nb record recover <id> --force           # Overwrite an existing note
    """
    if not _check_recorder_available():
        raise SystemExit(1)

    from nb.core.notebooks import get_default_transcript_notebook
    from nb.recorder.formatter import from_json, parse_speaker_names

    config = get_config()
    recordings_dir = config.nb_dir / "recordings"
    target_notebook = notebook or get_default_transcript_notebook()

    # No ID: list transcripts that have no note anywhere under notes_root.
    # We match by note filename (<recording_id>.md) rather than checking a
    # single notebook, so notes saved to non-default notebooks aren't reported
    # as missing.
    if not recording_id:
        jsons = sorted(recordings_dir.glob("*.json")) if recordings_dir.exists() else []
        if not jsons:
            console.print("[dim]No transcripts found.[/dim]")
            return

        existing_notes = {p.stem for p in config.notes_root.rglob("*.md")}
        orphans = [jp.stem for jp in jsons if jp.stem not in existing_notes]

        if not orphans:
            console.print("[green]All transcripts have a note.[/green]")
            return

        console.print("[bold]Transcripts with no note:[/bold]\n")
        for stem in orphans:
            console.print(f"  {stem}")
        console.print("\n[dim]Recover one with: nb record recover <recording_id>[/dim]")
        return

    # Find the JSON (exact match, then suffix match like 'transcribe' does)
    json_path = recordings_dir / f"{recording_id}.json"
    if not json_path.exists():
        matches = list(recordings_dir.glob(f"*_{recording_id}.json"))
        if matches:
            json_path = matches[0]
        else:
            console.print(f"[red]Transcript not found: {recording_id}[/red]")
            console.print(
                "[dim]Run 'nb record recover' to list transcripts missing a note.[/dim]"
            )
            raise SystemExit(1)

    try:
        loaded = from_json(json_path)
    except Exception as e:
        console.print(f"[red]Failed to read transcript: {e}[/red]")
        raise SystemExit(1) from e

    if not loaded.result.utterances:
        console.print(f"[yellow]Transcript is empty: {json_path.name}[/yellow]")
        console.print(
            "[dim]Re-transcribe from audio with: nb record transcribe <id>[/dim]"
        )
        raise SystemExit(1)

    # Speaker names: CLI override wins, otherwise reuse the labels saved in the JSON
    speaker_names = parse_speaker_names(speakers) or loaded.speaker_names

    md_path = _resolve_note_path(
        target_notebook, loaded.result.recording_id, loaded.recorded_at
    )
    if md_path.exists() and not force:
        console.print(
            f"[yellow]Note already exists:[/yellow] {md_path.relative_to(config.notes_root)}"
        )
        console.print("[dim]Use --force to overwrite.[/dim]")
        raise SystemExit(1)

    console.print(f"[cyan]Rebuilding note from {json_path.name}...[/cyan]")
    _write_transcript_note(
        loaded.result,
        recording_id=loaded.result.recording_id,
        recorded_at=loaded.recorded_at,
        notebook=target_notebook,
        speaker_names=speaker_names,
        dictation=dictation,
        summarize=summarize,
    )

    console.print()
    console.print("[bold]Recovery complete[/bold]")
    console.print(f"  Duration: {_format_duration(loaded.result.duration)}")
    console.print(f"  Speakers: {len(loaded.result.speaker_ids)}")
    console.print(f"  Utterances: {len(loaded.result.utterances)}")


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


@record_group.command("test")
@click.option("--save", "-s", is_flag=True, help="Save working devices to config")
def record_test(save: bool) -> None:
    """Test audio devices and find the best configuration.

    Scans all audio devices, tests which ones actually work, and shows
    the recommended configuration for meeting recording.

    \b
    Examples:
      nb record test           # Test devices and show recommendations
      nb record test --save    # Test and save working config

    \b
    For meeting recording (Teams/Zoom), you need:
      - Microphone: captures your voice
      - System audio (Stereo Mix): captures other participants
    """
    if not _check_recorder_available():
        raise SystemExit(1)

    from nb.recorder.audio import (
        _is_loopback_device,
        _is_microphone_device,
        list_devices,
        test_device,
    )

    config = get_config()

    console.print("[bold]Testing audio devices...[/bold]\n")

    all_devices = list_devices()
    sample_rate = config.recorder.sample_rate

    # Test microphone devices
    console.print("[cyan]Microphones:[/cyan]")
    mic_candidates = [
        dev
        for dev in all_devices
        if dev.max_input_channels > 0 and _is_microphone_device(dev.name)
    ]

    working_mic = None
    # Pick the recommendation with the same API preference start_recording uses
    # (WASAPI first), so --save can't pin a worse device than auto-detection
    # would have chosen on its own.
    for dev in sorted(mic_candidates, key=_mic_api_rank):
        channels = min(1, dev.max_input_channels)
        works = test_device(dev.index, channels=channels, sample_rate=sample_rate)
        status = "[green]OK[/green]" if works else "[red]FAILED[/red]"
        api_tag = f" [dim]({dev.hostapi_name})[/dim]"
        console.print(f"  [{dev.index}] {dev.name}{api_tag} {status}")
        if works and working_mic is None:
            working_mic = dev

    if not mic_candidates:
        console.print("  [dim]No microphone devices found[/dim]")

    # Test system audio. WASAPI loopback is the preferred path and needs no
    # configured device, so report it before falling back to Stereo Mix.
    console.print("\n[cyan]System Audio (Loopback):[/cyan]")

    from nb.recorder.audio import get_default_output_name

    loopback_name = get_default_output_name()
    if loopback_name:
        console.print(
            f"  WASAPI loopback: {loopback_name} [green]OK[/green] "
            "[dim](current output device)[/dim]"
        )

    loopback_candidates = [
        dev
        for dev in all_devices
        if dev.max_input_channels > 0 and _is_loopback_device(dev.name)
    ]

    working_loopback = None
    for dev in loopback_candidates:
        channels = min(2, dev.max_input_channels)
        works = test_device(dev.index, channels=channels, sample_rate=sample_rate)
        status = "[green]OK[/green]" if works else "[red]FAILED[/red]"
        api_tag = f" [dim]({dev.hostapi_name})[/dim]"
        console.print(f"  [{dev.index}] {dev.name}{api_tag} {status}")
        if works and working_loopback is None:
            working_loopback = dev

    if not loopback_candidates:
        console.print("  [dim]No loopback devices found[/dim]")
        console.print(
            "  [yellow]Tip: Enable 'Stereo Mix' in Windows Sound settings > Recording[/yellow]"
        )

    # Show recommendations
    console.print("\n[bold]Recommendations:[/bold]")

    if working_mic:
        console.print(
            f"  Microphone: [{working_mic.index}] {working_mic.name} [green](working)[/green]"
        )
    else:
        console.print("  Microphone: [red]None found[/red]")

    if loopback_name:
        console.print(
            f"  System audio: {loopback_name} [green](WASAPI loopback)[/green]"
        )
        console.print(
            "    [dim]Follows the current Windows output device, so it keeps working "
            "with headphones.[/dim]"
        )
    elif working_loopback:
        console.print(
            f"  System audio: [{working_loopback.index}] {working_loopback.name} [green](working)[/green]"
        )
        console.print(
            "    [yellow]Stereo Mix only captures the onboard audio chip — participants "
            "will be missing if you play audio through headphones.[/yellow]"
        )
    else:
        console.print("  System audio: [yellow]None found[/yellow]")
        console.print(
            "    [dim]Recording will work with --mic-only but won't capture meeting participants.[/dim]"
        )

    # Show current config vs recommendations
    console.print("\n[bold]Current Config:[/bold]")
    console.print(f"  mic_device: {config.recorder.mic_device}")
    console.print(f"  loopback_device: {config.recorder.loopback_device}")

    # Check if config needs updating. Never pin a loopback_device when WASAPI
    # loopback is available: an explicit index opts back into the Stereo Mix
    # path, which is exactly the setup that silently drops participants.
    new_mic = working_mic.index if working_mic else None
    new_loopback = (
        None
        if loopback_name
        else (working_loopback.index if working_loopback else None)
    )
    needs_update = (
        config.recorder.mic_device != new_mic
        or config.recorder.loopback_device != new_loopback
    )

    if needs_update:
        if save:
            # Save to config (clears stale devices that no longer work)
            _save_device_config(new_mic, new_loopback)
            console.print("\n[green]Config updated![/green]")
            if working_mic:
                console.print(f"  recorder.mic_device = {working_mic.index}")
            else:
                console.print("  recorder.mic_device = [dim]cleared[/dim]")
            if new_loopback is not None:
                console.print(f"  recorder.loopback_device = {new_loopback}")
            elif loopback_name:
                console.print(
                    "  recorder.loopback_device = [dim]unset (uses WASAPI loopback)[/dim]"
                )
            else:
                console.print("  recorder.loopback_device = [dim]cleared[/dim]")
        else:
            console.print("\n[yellow]Config update recommended.[/yellow]")
            console.print(
                "[dim]Run with --save to update automatically, or manually:[/dim]"
            )
            if working_mic:
                console.print(
                    f"  nb config set recorder.mic_device {working_mic.index}"
                )
            if new_loopback is not None:
                console.print(
                    f"  nb config set recorder.loopback_device {new_loopback}"
                )
            elif loopback_name and config.recorder.loopback_device is not None:
                console.print(
                    "  nb config unset recorder.loopback_device  "
                    "[dim](pinning it disables WASAPI loopback)[/dim]"
                )
    else:
        console.print("\n[green]Config looks good![/green]")


def _save_device_config(mic_device: int | None, loopback_device: int | None) -> None:
    """Save device configuration to config file."""
    from nb.config import get_config_path

    config_path = get_config_path()
    if not config_path.exists():
        # Create minimal config
        content = "recorder:\n"
        if mic_device is not None:
            content += f"  mic_device: {mic_device}\n"
        if loopback_device is not None:
            content += f"  loopback_device: {loopback_device}\n"
        config_path.write_text(content)
        return

    # Update existing config
    import yaml

    with config_path.open() as f:
        data = yaml.safe_load(f) or {}

    if "recorder" not in data:
        data["recorder"] = {}

    # Always set both keys — None clears stale device indices
    data["recorder"]["mic_device"] = mic_device
    data["recorder"]["loopback_device"] = loopback_device

    with config_path.open("w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _recording_spinner_fallback(
    session: RecordingSession,
    timeout_seconds: int | None,
) -> str:
    """Fallback recording loop when Wijjit is not available.

    Uses a simple Rich spinner with timeout support.
    Returns empty string (no notes support without Wijjit).
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    stop_requested = False

    def signal_handler(sig: int, frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        desc = "Recording"
        if timeout_seconds:
            desc += f" (auto-stop in {timeout_seconds // 60} min)"
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            _task = progress.add_task(desc, total=None)
            while session.is_recording and not stop_requested:
                time.sleep(0.25)
                if session._error:
                    progress.stop()
                    console.print(f"[red]Recording error: {session._error}[/red]")
                    raise SystemExit(1)
                if timeout_seconds and session.duration >= timeout_seconds:
                    console.print("[yellow]Auto-stop: duration limit reached.[/yellow]")
                    stop_requested = True
    except KeyboardInterrupt:
        pass

    return ""


def _mic_api_rank(dev: object) -> int:
    """Host-API preference for microphones: WASAPI > DirectSound > MME > rest.

    Mirrors `find_best_devices` so `nb record test` recommends the same device
    auto-detection would pick.
    """
    name = getattr(dev, "hostapi_name", "")
    for rank, api in enumerate(("WASAPI", "DirectSound", "MME")):
        if api in name:
            return rank
    return 3


def _report_levels(session: RecordingSession, mode: object) -> None:
    """Report captured level per channel, flagging any dead source.

    A silent channel means a source was never actually recorded (the classic
    case: Stereo Mix while playback is on headphones). That used to be
    invisible until you played the file back, so surface it immediately.
    """
    import math

    stats = getattr(session, "level_stats", None)
    if not stats:
        return

    from nb.recorder.audio import RecordingMode

    if mode == RecordingMode.MIC_ONLY:
        labels = ["mic"]
    elif mode == RecordingMode.SYSTEM_ONLY:
        labels = ["system", "system"]
    else:
        labels = ["mic", "system"]

    for st in stats:
        idx = int(st["channel"])
        label = labels[idx] if idx < len(labels) else f"ch{idx}"
        rms = float(st["rms"])
        if st["silent"]:
            console.print(
                f"    [red]{label}: SILENT[/red] "
                "[dim]— nothing was captured on this channel[/dim]"
            )
            continue
        dbfs = 20 * math.log10(rms) if rms > 0 else -99.0
        gain = float(st["gain"])
        gain_str = (
            f", normalized +{20 * math.log10(gain):.0f} dB" if gain > 1.01 else ""
        )
        console.print(f"    [dim]{label}: {dbfs:.0f} dBFS{gain_str}[/dim]")

    switches = getattr(session, "loopback_switches", 0)
    if switches:
        plural = "s" if switches > 1 else ""
        console.print(
            f"    [dim]system: followed {switches} output device change{plural} "
            f"(now {session.loopback_name})[/dim]"
        )

    dropped = getattr(session, "loopback_dropped_frames", 0)
    if dropped and session.sample_rate:
        seconds = dropped / session.sample_rate
        if seconds >= 0.5:
            console.print(
                f"    [yellow]System audio: ~{seconds:.1f}s dropped[/yellow] "
                "[dim](machine was too busy to keep up)[/dim]"
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


def _transcript_title(recording_id: str, dictation: bool) -> str:
    """Build a note title from a recording ID (e.g. "2025-12-01_1430_standup")."""
    parts = recording_id.split("_", 2)  # date_time_name
    if len(parts) >= 2:
        name = parts[-1] if len(parts) > 2 else parts[1]
        pretty = name.replace("-", " ").replace("_", " ").title()
        return f"Voice Note: {pretty}" if dictation else f"Meeting: {pretty}"
    return "Voice Note" if dictation else f"Meeting: {recording_id}"


def _resolve_note_path(notebook: str, recording_id: str, recorded_at: datetime) -> Path:
    """Compute the markdown note path for a recording (no directories created).

    For date-based notebooks the date is taken from the recording ID prefix,
    falling back to ``recorded_at`` if the prefix isn't a parseable date.
    """
    from nb.core.notebooks import is_notebook_date_based

    config = get_config()
    nb_path = config.get_notebook_path(notebook) or (config.notes_root / notebook)

    if is_notebook_date_based(notebook):
        from nb.utils.dates import get_week_folder_name

        date_str = recording_id.split("_", 1)[0]
        try:
            recording_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            recording_date = recorded_at.date()
        week_folder = (
            nb_path / str(recording_date.year) / get_week_folder_name(recording_date)
        )
        return week_folder / f"{recording_id}.md"

    return nb_path / f"{recording_id}.md"


def _write_transcript_note(
    result: TranscriptResult,
    recording_id: str,
    recorded_at: datetime,
    notebook: str | None = None,
    speaker_names: dict[int, str] | None = None,
    dictation: bool = False,
    user_notes: str | None = None,
    summarize: bool = False,
) -> Path:
    """Build the markdown note for a transcript and write it to the notebook.

    Shared by ``nb record start``/``transcribe`` (live transcription) and
    ``nb record recover`` (rebuild from an existing JSON). Resolves the target
    notebook and path, optionally generates LLM meeting notes, writes the
    markdown, and returns the note path. Parent directories are created by
    ``to_markdown``.
    """
    from nb.recorder.formatter import to_markdown

    config = get_config()

    if notebook is None:
        from nb.core.notebooks import get_default_transcript_notebook

        notebook = get_default_transcript_notebook()

    title = _transcript_title(recording_id, dictation)
    md_path = _resolve_note_path(notebook, recording_id, recorded_at)

    # Generate meeting notes with LLM if requested
    meeting_summary = None
    if summarize and not dictation and result.full_text.strip():
        from nb.recorder.meeting_notes import generate_meeting_notes

        meeting_summary = generate_meeting_notes(result.full_text)
        if meeting_summary:
            console.print("[green]Meeting notes generated.[/green]")

    tags = ["voice-note", "dictation"] if dictation else ["meeting", "transcript"]
    to_markdown(
        result,
        md_path,
        title=title,
        recorded_at=recorded_at,
        speaker_names=speaker_names,
        tags=tags,
        user_notes=user_notes,
        meeting_summary=meeting_summary,
    )
    console.print(
        f"[green]Transcript saved:[/green] {md_path.relative_to(config.notes_root)}"
    )
    return md_path


def _transcribe_recording(
    wav_path: Path,
    notebook: str | None = None,
    speakers: str | None = None,
    attendees: str | None = None,
    delete_audio: bool = False,
    dictation: bool = False,
    user_notes: str | None = None,
    summarize: bool = False,
) -> None:
    """Transcribe a recording and save outputs."""
    from nb.recorder.formatter import (
        parse_attendees,
        parse_speaker_names,
        to_json,
    )
    from nb.recorder.transcriber import get_api_key, transcribe

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

    # Build and write the markdown note (notebook resolution, path, LLM notes)
    _write_transcript_note(
        result,
        recording_id=wav_path.stem,
        recorded_at=datetime.now(),
        notebook=notebook,
        speaker_names=speaker_names,
        dictation=dictation,
        user_notes=user_notes,
        summarize=summarize,
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
