"""Tests for the recorder module.

Tests formatter functions and CLI command structure.
Audio recording tests are limited since they require actual audio devices.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from nb import config as config_module
from nb.cli import cli
from nb.config import Config, EmbeddingsConfig, NotebookConfig
from nb.index import scanner as scanner_module
from nb.index.db import reset_db

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def cli_runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def cli_config(tmp_path: Path):
    """Set up isolated config for CLI tests."""
    notes_root = tmp_path / "notes"
    notes_root.mkdir()
    nb_dir = notes_root / ".nb"
    nb_dir.mkdir()

    cfg = Config(
        notes_root=notes_root,
        editor="echo",
        notebooks=[
            NotebookConfig(name="daily", date_based=True),
            NotebookConfig(name="projects", date_based=False),
            NotebookConfig(name="work", date_based=False),
        ],
        embeddings=EmbeddingsConfig(),
        date_format="%Y-%m-%d",
        time_format="%H:%M",
    )

    # Create notebook directories
    for nb in cfg.notebooks:
        if not nb.is_external:
            (notes_root / nb.name).mkdir(exist_ok=True)

    scanner_module.ENABLE_VECTOR_INDEXING = False

    yield cfg

    config_module.reset_config()
    reset_db()


@pytest.fixture
def mock_cli_config(cli_config: Config, monkeypatch: pytest.MonkeyPatch):
    """Mock get_config() for CLI tests."""
    config_module.reset_config()
    monkeypatch.setattr(config_module, "_config", cli_config)
    return cli_config


# =============================================================================
# Formatter Tests
# =============================================================================


class TestFormatter:
    """Tests for nb.recorder.formatter functions."""

    def test_format_duration_seconds(self):
        from nb.recorder.formatter import format_duration

        assert format_duration(45) == "0:45"
        assert format_duration(0) == "0:00"

    def test_format_duration_minutes(self):
        from nb.recorder.formatter import format_duration

        assert format_duration(90) == "1:30"
        assert format_duration(754) == "12:34"
        assert format_duration(3599) == "59:59"

    def test_format_duration_hours(self):
        from nb.recorder.formatter import format_duration

        assert format_duration(3600) == "1:00:00"
        assert format_duration(3661) == "1:01:01"
        assert format_duration(5025) == "1:23:45"

    def test_format_timestamp(self):
        from nb.recorder.formatter import format_timestamp

        assert format_timestamp(0) == "[0:00]"
        assert format_timestamp(65) == "[1:05]"
        assert format_timestamp(3665) == "[1:01:05]"

    def test_parse_speaker_names_empty(self):
        from nb.recorder.formatter import parse_speaker_names

        assert parse_speaker_names(None) == {}
        assert parse_speaker_names("") == {}

    def test_parse_speaker_names_single(self):
        from nb.recorder.formatter import parse_speaker_names

        result = parse_speaker_names("0:Alice")
        assert result == {0: "Alice"}

    def test_parse_speaker_names_multiple(self):
        from nb.recorder.formatter import parse_speaker_names

        result = parse_speaker_names("0:Alice,1:Bob,2:Charlie")
        assert result == {0: "Alice", 1: "Bob", 2: "Charlie"}

    def test_parse_speaker_names_with_spaces(self):
        from nb.recorder.formatter import parse_speaker_names

        result = parse_speaker_names("0: Alice , 1: Bob Smith")
        assert result == {0: "Alice", 1: "Bob Smith"}

    def test_parse_speaker_names_invalid(self):
        from nb.recorder.formatter import parse_speaker_names

        # Invalid entries should be skipped
        result = parse_speaker_names("invalid,0:Alice,also:invalid:too")
        assert result == {0: "Alice"}

    def test_parse_attendees_empty(self):
        from nb.recorder.formatter import parse_attendees

        assert parse_attendees(None) == []
        assert parse_attendees("") == []

    def test_parse_attendees_single(self):
        from nb.recorder.formatter import parse_attendees

        assert parse_attendees("Alice") == ["Alice"]

    def test_parse_attendees_multiple(self):
        from nb.recorder.formatter import parse_attendees

        result = parse_attendees("Alice, Bob, Charlie")
        assert result == ["Alice", "Bob", "Charlie"]

    def test_parse_attendees_strips_whitespace(self):
        from nb.recorder.formatter import parse_attendees

        result = parse_attendees("  Alice  ,  Bob  ")
        assert result == ["Alice", "Bob"]


class TestFormatterOutput:
    """Tests for JSON and Markdown output generation."""

    def test_to_json(self, tmp_path: Path):
        from nb.recorder.formatter import to_json
        from nb.recorder.transcriber import TranscriptResult, Utterance

        result = TranscriptResult(
            recording_id="2025-12-01_test",
            duration=123.45,
            utterances=[
                Utterance(speaker=0, channel=0, start=0.0, end=5.0, text="Hello world"),
                Utterance(speaker=1, channel=1, start=5.5, end=10.0, text="Hi there"),
            ],
        )

        output_path = tmp_path / "test.json"
        to_json(result, output_path, speaker_names={0: "Alice", 1: "Bob"})

        assert output_path.exists()
        import json

        data = json.loads(output_path.read_text())

        assert data["meta"]["recording_id"] == "2025-12-01_test"
        assert data["meta"]["duration_seconds"] == 123.45
        assert len(data["utterances"]) == 2
        assert data["speakers"]["0"]["label"] == "Alice"
        assert data["speakers"]["1"]["label"] == "Bob"

    def test_to_markdown(self, tmp_path: Path):
        from nb.recorder.formatter import to_markdown
        from nb.recorder.transcriber import TranscriptResult, Utterance

        result = TranscriptResult(
            recording_id="2025-12-01_test",
            duration=123.45,
            utterances=[
                Utterance(speaker=0, channel=0, start=0.0, end=5.0, text="Hello world"),
                Utterance(speaker=1, channel=1, start=5.5, end=10.0, text="Hi there"),
            ],
        )

        output_path = tmp_path / "test.md"
        to_markdown(
            result,
            output_path,
            title="Test Meeting",
            speaker_names={0: "Alice", 1: "Bob"},
        )

        assert output_path.exists()
        content = output_path.read_text()

        assert "# Test Meeting" in content
        assert "**Alice** [0:00]:" in content
        assert "**Bob** [0:05]:" in content
        assert "Hello world" in content
        assert "Hi there" in content
        assert "duration: 2:03" in content

    def test_to_markdown_groups_consecutive_speaker(self, tmp_path: Path):
        from nb.recorder.formatter import to_markdown
        from nb.recorder.transcriber import TranscriptResult, Utterance

        result = TranscriptResult(
            recording_id="test",
            duration=30.0,
            utterances=[
                Utterance(speaker=0, channel=0, start=0.0, end=5.0, text="First."),
                Utterance(speaker=0, channel=0, start=5.0, end=10.0, text="Second."),
                Utterance(speaker=1, channel=1, start=10.0, end=15.0, text="Response."),
            ],
        )

        output_path = tmp_path / "test.md"
        to_markdown(result, output_path)

        content = output_path.read_text()
        # Should group "First. Second." from speaker 0
        assert "First. Second." in content


# =============================================================================
# Transcriber Tests
# =============================================================================


class TestTranscriber:
    """Tests for nb.recorder.transcriber functions."""

    def test_utterance_dataclass(self):
        from nb.recorder.transcriber import Utterance

        u = Utterance(
            speaker=0,
            channel=0,
            start=1.5,
            end=3.0,
            text="Hello",
            confidence=0.95,
        )
        assert u.speaker == 0
        assert u.text == "Hello"
        assert u.confidence == 0.95

    def test_transcript_result_properties(self):
        from nb.recorder.transcriber import TranscriptResult, Utterance

        result = TranscriptResult(
            recording_id="test",
            duration=60.0,
            utterances=[
                Utterance(speaker=0, channel=0, start=0.0, end=5.0, text="Hello"),
                Utterance(speaker=1, channel=1, start=5.0, end=10.0, text="Hi"),
                Utterance(speaker=0, channel=0, start=10.0, end=15.0, text="Bye"),
            ],
        )

        assert result.speaker_ids == {0, 1}
        assert result.full_text == "Hello Hi Bye"

    def test_get_api_key_from_env(self, monkeypatch):
        from nb.recorder.transcriber import get_api_key

        monkeypatch.setenv("DEEPGRAM_API_KEY", "test_key_123")
        assert get_api_key() == "test_key_123"

    def test_get_api_key_missing(self, monkeypatch):
        from nb.recorder.transcriber import get_api_key

        monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
        assert get_api_key() is None


# =============================================================================
# CLI Tests
# =============================================================================


class TestRecordCLI:
    """Tests for record CLI commands."""

    def test_record_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["record", "--help"])

        assert result.exit_code == 0
        assert "Record meetings" in result.output
        assert "start" in result.output
        assert "transcribe" in result.output
        assert "purge" in result.output

    def test_record_start_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["record", "start", "--help"])

        assert result.exit_code == 0
        assert "--name" in result.output
        assert "--notebook" in result.output
        assert "--audio-only" in result.output
        assert "--mic-only" in result.output
        assert "--system-only" in result.output
        assert "--delete-audio" in result.output

    def test_record_transcribe_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["record", "transcribe", "--help"])

        assert result.exit_code == 0
        assert "--speakers" in result.output
        assert "--attendees" in result.output

    def test_record_devices_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["record", "devices", "--help"])

        assert result.exit_code == 0
        assert "audio devices" in result.output.lower()

    def test_record_list_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["record", "list", "--help"])

        assert result.exit_code == 0
        assert "--status" in result.output

    def test_rec_alias(self, cli_runner: CliRunner):
        """Test that 'rec' alias works for 'record'."""
        result = cli_runner.invoke(cli, ["rec", "--help"])

        assert result.exit_code == 0
        assert "Record meetings" in result.output

    def test_record_list_empty(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test record list with no recordings."""
        result = cli_runner.invoke(cli, ["record", "list"])

        assert result.exit_code == 0
        assert "No recordings" in result.output

    def test_record_transcribe_no_id(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test transcribe without recording ID shows list."""
        result = cli_runner.invoke(cli, ["record", "transcribe"])

        assert result.exit_code == 0
        assert (
            "No recordings found" in result.output
            or "Recent recordings" in result.output
        )

    def test_transcribe_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["transcribe", "--help"])

        assert result.exit_code == 0
        assert "AUDIO_FILE" in result.output
        assert "--name" in result.output
        assert "--notebook" in result.output
        assert "--speakers" in result.output
        assert "--copy" in result.output

    def test_transcribe_missing_file(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test transcribe command with non-existent file."""
        result = cli_runner.invoke(cli, ["transcribe", "/nonexistent/file.wav"])

        assert result.exit_code != 0

    def test_record_purge_help(self, cli_runner: CliRunner):
        result = cli_runner.invoke(cli, ["record", "purge", "--help"])

        assert result.exit_code == 0
        assert "--transcribed" in result.output
        assert "--all" in result.output
        assert "--older-than" in result.output
        assert "--dry-run" in result.output

    def test_record_purge_empty(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test purge with no recordings directory."""
        result = cli_runner.invoke(cli, ["record", "purge", "--yes"])

        assert result.exit_code == 0
        assert "No recordings" in result.output

    def test_record_purge_no_files(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test purge with empty recordings directory."""
        recordings_dir = mock_cli_config.nb_dir / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)

        result = cli_runner.invoke(cli, ["record", "purge", "--yes"])

        assert result.exit_code == 0
        assert "No recordings to purge" in result.output

    def test_record_purge_dry_run(self, cli_runner: CliRunner, mock_cli_config: Config):
        """Test purge dry run shows files without deleting."""
        recordings_dir = mock_cli_config.nb_dir / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)

        # Create a transcribed recording (WAV + JSON)
        wav_file = recordings_dir / "2025-12-01_test.wav"
        json_file = recordings_dir / "2025-12-01_test.json"
        wav_file.write_bytes(b"fake audio")
        json_file.write_text("{}")

        result = cli_runner.invoke(cli, ["record", "purge", "--dry-run", "--yes"])

        assert result.exit_code == 0
        assert "Would delete" in result.output
        assert wav_file.exists()  # File should NOT be deleted

    def test_record_purge_transcribed_only(
        self, cli_runner: CliRunner, mock_cli_config: Config
    ):
        """Test purge only deletes transcribed recordings by default."""
        recordings_dir = mock_cli_config.nb_dir / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)

        # Create a transcribed recording
        transcribed_wav = recordings_dir / "2025-12-01_done.wav"
        transcribed_json = recordings_dir / "2025-12-01_done.json"
        transcribed_wav.write_bytes(b"fake audio")
        transcribed_json.write_text("{}")

        # Create a pending recording (no JSON)
        pending_wav = recordings_dir / "2025-12-01_pending.wav"
        pending_wav.write_bytes(b"fake audio")

        result = cli_runner.invoke(cli, ["record", "purge", "--yes"])

        assert result.exit_code == 0
        assert not transcribed_wav.exists()  # Should be deleted
        assert pending_wav.exists()  # Should NOT be deleted
        assert transcribed_json.exists()  # JSON preserved


# =============================================================================
# Audio Module Tests (limited - requires actual devices)
# =============================================================================


class TestAudioModule:
    """Basic tests for audio module (without actual recording)."""

    def test_audio_device_dataclass(self):
        from nb.recorder.audio import AudioDevice

        device = AudioDevice(
            index=0,
            name="Test Mic",
            hostapi=0,
            hostapi_name="WASAPI",
            max_input_channels=2,
            max_output_channels=0,
            default_samplerate=44100.0,
        )

        assert device.is_input is True
        assert device.is_output is False
        assert device.is_loopback is False

    def test_recording_session_dataclass(self, tmp_path: Path):
        from nb.recorder.audio import RecordingSession

        session = RecordingSession(
            output_path=tmp_path / "test.wav",
            mic_device=0,
            loopback_device=1,
            sample_rate=16000,
        )

        assert session.is_recording is False
        assert session.duration >= 0

    def test_recording_session_wait_for_start(self, tmp_path: Path):
        """Test that wait_for_start returns False on timeout."""
        from nb.recorder.audio import RecordingSession

        session = RecordingSession(
            output_path=tmp_path / "test.wav",
            mic_device=0,
            loopback_device=1,
            sample_rate=16000,
        )

        # Should timeout immediately since nothing started
        result = session.wait_for_start(timeout=0.1)
        assert result is False

    def test_recording_mode_enum(self):
        from nb.recorder.audio import RecordingMode

        assert RecordingMode.BOTH.value == "both"
        assert RecordingMode.MIC_ONLY.value == "mic"
        assert RecordingMode.SYSTEM_ONLY.value == "system"

    def test_get_recording_path(self, tmp_path: Path):
        from nb.recorder.audio import get_recording_path

        path = get_recording_path("standup", tmp_path)

        assert path.parent == tmp_path
        assert path.suffix == ".wav"
        assert "standup" in path.name
        # Date prefix format: YYYY-MM-DD
        assert path.name.count("-") >= 2


# =============================================================================
# Recorder Package Tests
# =============================================================================


class TestRecorderPackage:
    """Tests for nb.recorder package."""

    def test_is_available_function_exists(self):
        from nb.recorder import is_available

        # Should return bool (True if deps installed, False otherwise)
        result = is_available()
        assert isinstance(result, bool)

    def test_require_recorder_function_exists(self):
        from nb.recorder import require_recorder

        # Function should exist and be callable
        assert callable(require_recorder)


# =============================================================================
# RecorderConfig Tests
# =============================================================================


class TestRecorderConfig:
    """Tests for recorder configuration."""

    def test_recorder_config_defaults(self):
        from nb.config import RecorderConfig

        config = RecorderConfig()
        assert config.mic_device is None
        assert config.loopback_device is None
        assert config.sample_rate == 16000
        assert config.auto_delete_audio is False

    def test_recorder_config_custom_values(self):
        from nb.config import RecorderConfig

        config = RecorderConfig(
            mic_device=1,
            loopback_device=3,
            sample_rate=44100,
            auto_delete_audio=True,
        )
        assert config.mic_device == 1
        assert config.loopback_device == 3
        assert config.sample_rate == 44100
        assert config.auto_delete_audio is True

    def test_parse_recorder_config_empty(self):
        from nb.config import _parse_recorder_config

        config = _parse_recorder_config(None)
        assert config.mic_device is None
        assert config.sample_rate == 16000

    def test_parse_recorder_config_with_data(self):
        from nb.config import _parse_recorder_config

        data = {
            "mic_device": 2,
            "loopback_device": 5,
            "sample_rate": 48000,
            "auto_delete_audio": True,
        }
        config = _parse_recorder_config(data)
        assert config.mic_device == 2
        assert config.loopback_device == 5
        assert config.sample_rate == 48000
        assert config.auto_delete_audio is True

    def test_config_has_recorder_field(self, cli_config: Config):
        """Test that Config has recorder field with defaults."""
        from nb.config import RecorderConfig

        assert hasattr(cli_config, "recorder")
        assert isinstance(cli_config.recorder, RecorderConfig)
