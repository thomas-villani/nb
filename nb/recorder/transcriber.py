"""Transcription functionality using Deepgram API.

Handles audio upload, transcription with speaker diarization,
and parsing of results.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Utterance:
    """A single utterance (speech segment) from transcription."""

    speaker: int  # Speaker ID (0 = mic/you, 1+ = others)
    channel: int  # 0 = left (mic), 1 = right (system)
    start: float  # Start time in seconds
    end: float  # End time in seconds
    text: str  # Transcribed text
    confidence: float = 0.0  # Confidence score (0-1)


@dataclass
class TranscriptResult:
    """Complete transcription result."""

    recording_id: str
    duration: float  # Total duration in seconds
    utterances: list[Utterance] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def speaker_ids(self) -> set[int]:
        """Get unique speaker IDs in the transcript."""
        return {u.speaker for u in self.utterances}

    @property
    def full_text(self) -> str:
        """Get the full transcript as a single string."""
        return " ".join(u.text for u in self.utterances)


def get_api_key() -> str | None:
    """Get Deepgram API key from environment or config.

    Checks in order:
    1. DEEPGRAM_API_KEY environment variable
    2. nb recorder config (future)

    Returns:
        API key or None if not found
    """
    return os.environ.get("DEEPGRAM_API_KEY")


def _parse_deepgram_response(
        response: dict[str, Any], recording_id: str
) -> TranscriptResult:
    """Parse Deepgram API response into TranscriptResult.

    Args:
        response: Raw Deepgram API response
        recording_id: ID for this recording

    Returns:
        Parsed TranscriptResult
    """
    utterances: list[Utterance] = []
    duration = 0.0

    results = response.get("results", {})

    # Get duration from metadata
    if "metadata" in response:
        duration = response["metadata"].get("duration", 0.0)

    # Handle multichannel results
    # When multichannel + diarize are both enabled, each channel gets independent
    # speaker IDs starting from 0. We offset channel 1+ speakers to make IDs unique.
    # Channel 0 (mic) speaker 0 = "You", Channel 1 (system) speakers = 100, 101, etc.
    channels = results.get("channels", [])
    for channel_idx, channel in enumerate(channels):
        alternatives = channel.get("alternatives", [])
        if not alternatives:
            continue

        # Use best alternative
        alt = alternatives[0]

        # If we have word-level data with speaker info, use that
        words = alt.get("words", [])
        if words:
            # Group words into utterances by speaker
            current_speaker = None
            current_words: list[dict] = []

            for word in words:
                raw_speaker = word.get("speaker", 0)
                # Offset speaker IDs by channel to ensure uniqueness
                speaker = raw_speaker + (channel_idx * 100)
                if current_speaker is None:
                    current_speaker = speaker

                if speaker != current_speaker:
                    # Emit current utterance
                    if current_words:
                        utterances.append(
                            Utterance(
                                speaker=current_speaker,
                                channel=channel_idx,
                                start=current_words[0].get("start", 0.0),
                                end=current_words[-1].get("end", 0.0),
                                text=" ".join(w.get("word", "") for w in current_words),
                                confidence=sum(
                                    w.get("confidence", 0.0) for w in current_words
                                )
                                           / len(current_words),
                            )
                        )
                    current_words = [word]
                    current_speaker = speaker
                else:
                    current_words.append(word)

            # Emit final utterance
            if current_words and current_speaker is not None:
                utterances.append(
                    Utterance(
                        speaker=current_speaker,
                        channel=channel_idx,
                        start=current_words[0].get("start", 0.0),
                        end=current_words[-1].get("end", 0.0),
                        text=" ".join(w.get("word", "") for w in current_words),
                        confidence=sum(w.get("confidence", 0.0) for w in current_words)
                                   / len(current_words),
                    )
                )
        else:
            # Fall back to paragraph/sentence level
            paragraphs = alt.get("paragraphs", {}).get("paragraphs", [])
            for para in paragraphs:
                for sentence in para.get("sentences", []):
                    utterances.append(
                        Utterance(
                            speaker=para.get("speaker", channel_idx),
                            channel=channel_idx,
                            start=sentence.get("start", 0.0),
                            end=sentence.get("end", 0.0),
                            text=sentence.get("text", ""),
                        )
                    )

    # Sort by start time
    utterances.sort(key=lambda u: u.start)

    return TranscriptResult(
        recording_id=recording_id,
        duration=duration,
        utterances=utterances,
        raw_response=response,
    )


def transcribe_file(
        audio_path: Path,
        api_key: str | None = None,
        model: str = "nova-2",
        dictation: bool = False,
        timeout: int = 600,
) -> TranscriptResult:
    """Transcribe an audio file using Deepgram (v5 SDK).

    Args:
        audio_path: Path to the audio file (WAV format preferred)
        api_key: Deepgram API key (uses env var if not provided)
        model: Deepgram model to use (default: nova-2)
        dictation: If True, optimize for single-speaker dictation/voice notes
        timeout: API timeout in seconds (default: 600 = 10 minutes)

    Returns:
        TranscriptResult with utterances and metadata

    Raises:
        ImportError: If deepgram-sdk is not installed
        ValueError: If API key is not available
        RuntimeError: If transcription fails
    """
    try:
        from deepgram import DeepgramClient
        from deepgram.core import RequestOptions
    except ImportError as e:
        raise ImportError(
            "Deepgram SDK required for transcription.\n"
            "Install with: uv sync --extra recorder"
        ) from e

    if api_key is None:
        api_key = get_api_key()
    if not api_key:
        raise ValueError(
            "Deepgram API key not found.\n"
            "Set DEEPGRAM_API_KEY environment variable or configure in nb."
        )

    # Read audio file
    with audio_path.open("rb") as f:
        audio_data = f.read()

    # Create client
    client = DeepgramClient(api_key=api_key)

    # Request options with timeout for large files
    request_options = RequestOptions(timeout_in_seconds=timeout, max_retries=3)

    # Build options dict - v5 API passes parameters directly
    if dictation:
        # Optimized for single-speaker dictation/voice notes
        options = {
            "model": model,
            "punctuate": True,
            "dictation": True,
            "smart_format": True,
            "paragraphs": True,
            "utterances": True,
        }
    else:
        # Default: meeting recording with multiple speakers
        options = {
            "model": model,
            "multichannel": True,
            "punctuate": True,
            "diarize": True,
            "utterances": True,
            "smart_format": True,
            "paragraphs": True,
        }

    try:
        # v5 API: pass audio data, options, and request settings
        response = client.listen.v1.media.transcribe_file(
            request=audio_data,
            request_options=request_options,
            **options,
        )
        # v5 SDK uses Pydantic models - use model_dump() or to_json()

        response_dict = response.model_dump()
    except Exception as e:
        raise RuntimeError(f"Transcription failed: {e!r}") from e

    # Parse response
    recording_id = audio_path.stem
    return _parse_deepgram_response(response_dict, recording_id)


def transcribe(
        audio_path: Path,
        api_key: str | None = None,
        model: str = "nova-2",
        dictation: bool = False,
        timeout: int = 600,
) -> TranscriptResult:
    """Transcribe an audio file using Deepgram.

    Args:
        audio_path: Path to the audio file (WAV format preferred)
        api_key: Deepgram API key (uses env var if not provided)
        model: Deepgram model to use (default: nova-2)
        dictation: If True, optimize for single-speaker dictation/voice notes
        timeout: API timeout in seconds (default: 600 = 10 minutes)

    Returns:
        TranscriptResult with utterances and metadata
    """
    return transcribe_file(audio_path, api_key, model, dictation, timeout)
