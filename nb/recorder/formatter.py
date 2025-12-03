"""Output formatting for transcripts.

Converts TranscriptResult to JSON and Markdown formats.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from nb.config import get_config
from nb.recorder.transcriber import TranscriptResult


def format_duration(seconds: float) -> str:
    """Format duration in seconds as HH:MM:SS or MM:SS.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string like "12:34" or "1:23:45"
    """
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_timestamp(seconds: float) -> str:
    """Format timestamp in seconds as [M:SS] or [H:MM:SS].

    Args:
        seconds: Time in seconds

    Returns:
        Formatted string like "[1:23]" or "[1:23:45]"
    """
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"[{hours}:{minutes:02d}:{secs:02d}]"
    return f"[{minutes}:{secs:02d}]"


def to_json(
        result: TranscriptResult,
        output_path: Path,
        source_file: str | None = None,
        recorded_at: datetime | None = None,
        speaker_names: dict[int, str] | None = None,
        attendees: list[str] | None = None,
) -> None:
    """Write transcript to JSON file.

    Args:
        result: TranscriptResult to convert
        output_path: Path for output JSON file
        source_file: Original audio filename (optional)
        recorded_at: Recording timestamp (defaults to now)
        speaker_names: Map of speaker IDs to names (optional)
        attendees: List of attendee names (optional, stored in metadata)
    """
    if recorded_at is None:
        recorded_at = datetime.now()

    # Build speaker info
    # Speaker 0 on channel 0 is the microphone (you)
    config = get_config()
    mic_label = config.recorder.mic_speaker_label
    speakers: dict[str, dict[str, Any]] = {}
    for speaker_id in result.speaker_ids:
        if speaker_names and speaker_id in speaker_names:
            label = speaker_names[speaker_id]
        elif speaker_id == 0:
            # Channel 0, speaker 0 = microphone
            label = mic_label
        else:
            label = f"Speaker {speaker_id}"
        # Determine channel from utterances
        channel = next(
            (u.channel for u in result.utterances if u.speaker == speaker_id), 0
        )
        speakers[str(speaker_id)] = {"label": label, "channel": channel}

    # Build utterances
    utterances = [
        {
            "speaker": u.speaker,
            "start": round(u.start, 2),
            "end": round(u.end, 2),
            "text": u.text,
        }
        for u in result.utterances
    ]

    # Build output structure
    data: dict[str, Any] = {
        "meta": {
            "recording_id": result.recording_id,
            "recorded_at": recorded_at.isoformat(),
            "duration_seconds": round(result.duration, 2),
        },
        "speakers": speakers,
        "utterances": utterances,
    }

    # Add optional metadata
    if source_file:
        data["meta"]["source_file"] = source_file
    if attendees:
        data["meta"]["attendees"] = attendees

    # Write file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def to_markdown(
        result: TranscriptResult,
        output_path: Path,
        title: str | None = None,
        recorded_at: datetime | None = None,
        speaker_names: dict[int, str] | None = None,
        include_frontmatter: bool = True,
        tags: list[str] | None = None,
) -> None:
    """Write transcript to Markdown file.

    Args:
        result: TranscriptResult to convert
        output_path: Path for output Markdown file
        title: Document title (defaults to "Meeting Transcript")
        recorded_at: Recording timestamp (defaults to now)
        speaker_names: Map of speaker IDs to names (optional)
        include_frontmatter: Whether to include YAML frontmatter
        tags: List of tags for frontmatter
    """
    if recorded_at is None:
        recorded_at = datetime.now()
    if title is None:
        title = "Meeting Transcript"

    lines: list[str] = []

    # Frontmatter
    if include_frontmatter:
        lines.append("---")
        lines.append(f"date: {recorded_at.strftime('%Y-%m-%d')}")
        if tags:
            lines.append(f"tags: [{', '.join(tags)}]")
        else:
            lines.append("tags: [meeting, transcript]")
        lines.append(f"duration: {format_duration(result.duration)}")
        lines.append("---")
        lines.append("")

    # Title and metadata
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Date:** {recorded_at.strftime('%Y-%m-%d %H:%M')}  ")
    lines.append(f"**Duration:** {format_duration(result.duration)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Group utterances to reduce repetition
    # Combine consecutive utterances from the same speaker
    grouped_utterances: list[tuple[int, float, str]] = []
    current_speaker: int | None = None
    current_start: float = 0.0
    current_texts: list[str] = []

    for u in result.utterances:
        if current_speaker is None:
            current_speaker = u.speaker
            current_start = u.start
            current_texts = [u.text]
        elif u.speaker == current_speaker:
            current_texts.append(u.text)
        else:
            # Emit current group
            grouped_utterances.append(
                (current_speaker, current_start, " ".join(current_texts))
            )
            current_speaker = u.speaker
            current_start = u.start
            current_texts = [u.text]

    # Emit final group
    if current_speaker is not None and current_texts:
        grouped_utterances.append(
            (current_speaker, current_start, " ".join(current_texts))
        )

    # Get mic speaker label from config
    config = get_config()
    mic_label = config.recorder.mic_speaker_label

    # Write utterances
    for speaker_id, start, text in grouped_utterances:
        if speaker_names and speaker_id in speaker_names:
            label = speaker_names[speaker_id]
        elif speaker_id == 0:
            # Channel 0, speaker 0 = microphone
            label = mic_label
        else:
            label = f"Speaker {speaker_id}"
        timestamp = format_timestamp(start)
        lines.append(f"**{label}** {timestamp}: {text}")
        lines.append("")

    # Write file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def parse_speaker_names(speaker_arg: str | None) -> dict[int, str]:
    """Parse speaker names from CLI argument.

    Args:
        speaker_arg: String like "0:Alice,1:Bob" or None

    Returns:
        Dict mapping speaker IDs to names
    """
    if not speaker_arg:
        return {}

    result: dict[int, str] = {}
    for pair in speaker_arg.split(","):
        pair = pair.strip()
        if ":" not in pair:
            continue
        id_str, name = pair.split(":", 1)
        try:
            speaker_id = int(id_str.strip())
            result[speaker_id] = name.strip()
        except ValueError:
            continue

    return result


def parse_attendees(attendees_arg: str | None) -> list[str]:
    """Parse attendees from CLI argument.

    Args:
        attendees_arg: Comma-separated string like "Alice,Bob,Charlie" or None

    Returns:
        List of attendee names
    """
    if not attendees_arg:
        return []

    return [name.strip() for name in attendees_arg.split(",") if name.strip()]
