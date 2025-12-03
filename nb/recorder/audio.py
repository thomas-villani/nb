"""Audio recording functionality using sounddevice and WASAPI.

Captures audio from microphone, system audio (loopback), or both.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nb.recorder import require_recorder

if TYPE_CHECKING:
    pass


class RecordingMode(Enum):
    """Audio recording mode."""

    BOTH = "both"  # Mic + system audio (stereo: left=mic, right=system)
    MIC_ONLY = "mic"  # Microphone only (mono)
    SYSTEM_ONLY = "system"  # System audio only (stereo or mono)


@dataclass
class AudioDevice:
    """Represents an audio device."""

    index: int
    name: str
    hostapi: int
    hostapi_name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float
    is_loopback: bool = False

    @property
    def is_input(self) -> bool:
        return self.max_input_channels > 0

    @property
    def is_output(self) -> bool:
        return self.max_output_channels > 0


@dataclass
class RecordingSession:
    """Active recording session."""

    output_path: Path
    mic_device: int | None
    loopback_device: int | None
    sample_rate: int
    mode: RecordingMode = RecordingMode.BOTH
    started_at: datetime = field(default_factory=datetime.now)
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _error: Exception | None = None
    _started: threading.Event = field(default_factory=threading.Event)
    # Stream and buffer references (set by start_recording)
    _mic_stream: Any = None  # sd.InputStream
    _loopback_stream: Any = None  # sd.InputStream
    _mic_buffer: list = field(default_factory=list)
    _loopback_buffer: list = field(default_factory=list)
    _buffer_lock: threading.Lock = field(default_factory=threading.Lock)

    def stop(self) -> None:
        """Signal the recording to stop."""
        self._stop_event.set()

    @property
    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def duration(self) -> float:
        """Duration in seconds since recording started."""
        return (datetime.now() - self.started_at).total_seconds()

    def wait_for_start(self, timeout: float = 5.0) -> bool:
        """Wait for recording to actually start capturing audio.

        Returns True if started successfully, False if timed out or error.
        """
        return self._started.wait(timeout=timeout)


def list_devices() -> list[AudioDevice]:
    """List all available audio devices.

    Returns devices with their capabilities (input/output channels, sample rates).
    WASAPI loopback devices are identified for system audio capture.
    """
    require_recorder()
    import sounddevice as sd

    devices = []
    hostapis = sd.query_hostapis()

    for i, dev in enumerate(sd.query_devices()):
        hostapi_idx = dev["hostapi"]
        hostapi_name = hostapis[hostapi_idx]["name"]

        # WASAPI loopback devices typically have specific characteristics
        is_loopback = "WASAPI" in hostapi_name and "loopback" in dev["name"].lower()

        devices.append(
            AudioDevice(
                index=i,
                name=dev["name"],
                hostapi=hostapi_idx,
                hostapi_name=hostapi_name,
                max_input_channels=dev["max_input_channels"],
                max_output_channels=dev["max_output_channels"],
                default_samplerate=dev["default_samplerate"],
                is_loopback=is_loopback,
            )
        )

    return devices


def get_wasapi_devices() -> tuple[list[AudioDevice], list[AudioDevice]]:
    """Get WASAPI input devices and loopback-capable output devices.

    Returns:
        Tuple of (input_devices, loopback_devices)
    """
    require_recorder()
    import sounddevice as sd

    devices = list_devices()
    hostapis = sd.query_hostapis()

    # Find WASAPI hostapi index
    wasapi_idx = None
    for i, api in enumerate(hostapis):
        if "WASAPI" in api["name"]:
            wasapi_idx = i
            break

    if wasapi_idx is None:
        return [], []

    # Filter for WASAPI devices
    inputs = [d for d in devices if d.hostapi == wasapi_idx and d.is_input]
    outputs = [d for d in devices if d.hostapi == wasapi_idx and d.is_output]

    return inputs, outputs


def find_default_devices() -> tuple[int | None, int | None]:
    """Find sensible default microphone and loopback devices.

    Returns:
        Tuple of (mic_device_index, loopback_device_index), either may be None
    """
    require_recorder()
    import sounddevice as sd

    mic_device = None
    loopback_device = None

    try:
        # Get default input device as mic
        default_input = sd.query_devices(kind="input")
        if default_input:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev["name"] == default_input["name"]:
                    mic_device = i
                    break
    except Exception:
        pass

    # Try to find a WASAPI loopback device
    inputs, outputs = get_wasapi_devices()

    # Look for explicit loopback device first
    for dev in inputs:
        if "loopback" in dev.name.lower():
            loopback_device = dev.index
            break

    # If no loopback found, try first WASAPI output (can be used with wasapi_loopback=True)
    if loopback_device is None and outputs:
        loopback_device = outputs[0].index

    return mic_device, loopback_device


def _writer_thread(session: RecordingSession) -> None:
    """Background thread that waits for stop signal and writes the audio file.

    Streams are started in the main thread (required for WASAPI on Windows).
    This thread just waits and writes the buffered data when stopped.
    """
    require_recorder()
    import numpy as np
    import soundfile as sf

    try:
        # Wait for stop signal
        while not session._stop_event.is_set():
            time.sleep(0.1)

        # Stop and close streams
        if session._mic_stream is not None:
            session._mic_stream.stop()
            session._mic_stream.close()
        if session._loopback_stream is not None:
            session._loopback_stream.stop()
            session._loopback_stream.close()

        # Write audio data to file
        mic_buffer = session._mic_buffer
        loopback_buffer = session._loopback_buffer
        sample_rate = session.sample_rate
        mode = session.mode

        with session._buffer_lock:
            if mic_buffer and loopback_buffer and mode == RecordingMode.BOTH:
                # Combine mic and loopback into stereo
                mic_data = np.concatenate(mic_buffer, axis=0)
                loopback_data = np.concatenate(loopback_buffer, axis=0)

                # Ensure same length (pad shorter with zeros)
                max_len = max(len(mic_data), len(loopback_data))
                if len(mic_data) < max_len:
                    pad_width = [(0, max_len - len(mic_data))]
                    if mic_data.ndim > 1:
                        pad_width.append((0, 0))
                    mic_data = np.pad(mic_data, pad_width)
                if len(loopback_data) < max_len:
                    pad_width = [(0, max_len - len(loopback_data))]
                    if loopback_data.ndim > 1:
                        pad_width.append((0, 0))
                    loopback_data = np.pad(loopback_data, pad_width)

                # Mic is mono -> left channel
                left_channel = (
                    mic_data[:, 0] if mic_data.ndim > 1 else mic_data.flatten()
                )

                # Loopback stereo -> mix to mono for right channel
                if loopback_data.ndim > 1 and loopback_data.shape[1] >= 2:
                    right_channel = (loopback_data[:, 0] + loopback_data[:, 1]) / 2
                else:
                    right_channel = loopback_data.flatten()

                # Ensure same length after processing
                min_len = min(len(left_channel), len(right_channel))
                stereo_data = np.column_stack(
                    [left_channel[:min_len], right_channel[:min_len]]
                )

                sf.write(
                    session.output_path, stereo_data, sample_rate, subtype="PCM_16"
                )

            elif mic_buffer:
                # Only mic data (mono)
                mic_data = np.concatenate(mic_buffer, axis=0)
                if mic_data.ndim > 1:
                    mic_data = mic_data[:, 0]
                sf.write(session.output_path, mic_data, sample_rate, subtype="PCM_16")

            elif loopback_buffer:
                # Only loopback data
                loopback_data = np.concatenate(loopback_buffer, axis=0)
                sf.write(
                    session.output_path, loopback_data, sample_rate, subtype="PCM_16"
                )

            else:
                raise ValueError("No audio data was captured")

    except Exception as e:
        session._error = e


def start_recording(
        output_path: Path,
        mic_device: int | None = None,
        loopback_device: int | None = None,
        sample_rate: int = 16000,
        mode: RecordingMode = RecordingMode.BOTH,
) -> RecordingSession:
    """Start recording audio to a file.

    Args:
        output_path: Path for the output WAV file
        mic_device: Device index for microphone (None for default)
        loopback_device: Device index for system audio loopback (None for default)
        sample_rate: Sample rate in Hz (default 16000 for speech)
        mode: Recording mode (BOTH, MIC_ONLY, or SYSTEM_ONLY)

    Returns:
        RecordingSession object to control and monitor the recording
    """
    require_recorder()
    import sounddevice as sd

    # Find defaults if not specified
    default_mic, default_loopback = find_default_devices()

    # Apply defaults based on mode
    if mode in (RecordingMode.BOTH, RecordingMode.MIC_ONLY):
        if mic_device is None:
            mic_device = default_mic
    if mode in (RecordingMode.BOTH, RecordingMode.SYSTEM_ONLY):
        if loopback_device is None:
            loopback_device = default_loopback

    # Validate we have required devices
    if mode == RecordingMode.MIC_ONLY and mic_device is None:
        raise ValueError("No microphone device found. Use --mic to specify one.")
    if mode == RecordingMode.SYSTEM_ONLY and loopback_device is None:
        raise ValueError("No system audio device found. Use --loopback to specify one.")
    if mode == RecordingMode.BOTH and mic_device is None and loopback_device is None:
        raise ValueError(
            "No audio devices found. Use --mic and/or --loopback to specify."
        )

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine which streams to open based on mode
    use_mic = (
            mode in (RecordingMode.BOTH, RecordingMode.MIC_ONLY) and mic_device is not None
    )
    use_loopback = (
            mode in (RecordingMode.BOTH, RecordingMode.SYSTEM_ONLY)
            and loopback_device is not None
    )

    # Shared buffers for callbacks
    mic_buffer: list = []
    loopback_buffer: list = []
    buffer_lock = threading.Lock()

    def mic_callback(indata, frames, time_info, status):
        with buffer_lock:
            mic_buffer.append(indata.copy())

    def loopback_callback(indata, frames, time_info, status):
        with buffer_lock:
            loopback_buffer.append(indata.copy())

    # Open and start streams in MAIN THREAD (required for WASAPI on Windows)
    mic_stream = None
    loopback_stream = None

    if use_mic:
        mic_info = sd.query_devices(mic_device)
        mic_channels = min(1, mic_info["max_input_channels"]) or 1
        mic_stream = sd.InputStream(
            device=mic_device,
            channels=mic_channels,
            samplerate=sample_rate,
            callback=mic_callback,
        )
        mic_stream.start()

    if use_loopback:
        loopback_info = sd.query_devices(loopback_device)
        loopback_channels = min(2, loopback_info["max_input_channels"]) or 1
        loopback_stream = sd.InputStream(
            device=loopback_device,
            channels=loopback_channels,
            samplerate=sample_rate,
            callback=loopback_callback,
        )
        loopback_stream.start()

    if mic_stream is None and loopback_stream is None:
        raise ValueError("Failed to open any audio streams")

    session = RecordingSession(
        output_path=output_path,
        mic_device=mic_device,
        loopback_device=loopback_device,
        sample_rate=sample_rate,
        mode=mode,
    )

    # Store streams and buffers in session for the writer thread
    session._mic_stream = mic_stream
    session._loopback_stream = loopback_stream
    session._mic_buffer = mic_buffer
    session._loopback_buffer = loopback_buffer
    session._buffer_lock = buffer_lock

    # Signal that recording has started (streams are already running)
    session._started.set()

    # Start writer thread (just waits for stop signal and writes file)
    session._thread = threading.Thread(
        target=_writer_thread,
        args=(session,),
        daemon=True,
    )
    session._thread.start()

    return session


def stop_recording(session: RecordingSession, timeout: float = 5.0) -> Path:
    """Stop a recording session and wait for file to be written.

    Args:
        session: The recording session to stop
        timeout: Maximum seconds to wait for recording to finish

    Returns:
        Path to the recorded audio file

    Raises:
        TimeoutError: If recording doesn't stop within timeout
        RuntimeError: If recording encountered an error
    """
    session.stop()

    if session._thread:
        session._thread.join(timeout=timeout)
        if session._thread.is_alive():
            raise TimeoutError("Recording thread did not stop within timeout")

    if session._error:
        raise RuntimeError(f"Recording failed: {session._error}") from session._error

    return session.output_path


def get_recording_path(name: str, recordings_dir: Path) -> Path:
    """Generate a recording file path with date and time prefix.

    Args:
        name: Base name for the recording (e.g., "standup")
        recordings_dir: Directory to store recordings

    Returns:
        Path like recordings_dir/2025-12-01_1430_standup.wav
    """
    datetime_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"{datetime_str}_{name}.wav"
    return recordings_dir / filename
