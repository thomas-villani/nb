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


def _is_microphone_device(name: str) -> bool:
    """Check if device name indicates a physical microphone."""
    name_lower = name.lower()
    mic_keywords = ["microphone", "mic array", "mic input", "headset"]
    exclude_keywords = ["stereo mix", "loopback", "what u hear", "wave out"]

    has_mic_keyword = any(kw in name_lower for kw in mic_keywords)
    has_exclude_keyword = any(kw in name_lower for kw in exclude_keywords)

    return has_mic_keyword and not has_exclude_keyword


def _is_loopback_device(name: str) -> bool:
    """Check if device name indicates system audio capture capability."""
    name_lower = name.lower()
    loopback_keywords = ["stereo mix", "loopback", "what u hear", "wave out", "mixage"]
    return any(kw in name_lower for kw in loopback_keywords)


def test_device(device_index: int, channels: int = 1, sample_rate: int = 16000) -> bool:
    """Test if a device can actually be opened for recording.

    Args:
        device_index: The device index to test
        channels: Number of channels to request
        sample_rate: Sample rate to request

    Returns:
        True if device can be opened successfully, False otherwise
    """
    require_recorder()
    import sounddevice as sd

    try:
        stream = sd.InputStream(
            device=device_index,
            channels=channels,
            samplerate=sample_rate,
        )
        stream.start()
        import time

        time.sleep(0.1)
        stream.stop()
        stream.close()
        return True
    except Exception:
        return False


def find_default_devices() -> tuple[int | None, int | None]:
    """Find sensible default microphone and loopback devices.

    Uses smart detection with the following priority:
    1. WASAPI devices (best quality/latency on Windows)
    2. DirectSound devices (good compatibility)
    3. MME devices (fallback)

    For loopback (system audio), looks for Stereo Mix or similar.

    Returns:
        Tuple of (mic_device_index, loopback_device_index), either may be None
    """
    require_recorder()
    import sounddevice as sd

    all_devices = list_devices()
    hostapis = sd.query_hostapis()

    # Find host API indices by priority
    api_priority = ["WASAPI", "DirectSound", "MME", "WDM-KS"]
    api_indices: dict[str, int] = {}
    for i, api in enumerate(hostapis):
        for api_name in api_priority:
            if api_name in api["name"]:
                api_indices[api_name] = i
                break

    # --- Find microphone device ---
    mic_device = None

    # Group microphone candidates by API
    mic_candidates: dict[str, list[AudioDevice]] = {api: [] for api in api_priority}
    for dev in all_devices:
        if dev.max_input_channels > 0 and _is_microphone_device(dev.name):
            for api_name in api_priority:
                if api_name in dev.hostapi_name:
                    mic_candidates[api_name].append(dev)
                    break

    # Try APIs in priority order
    for api_name in api_priority:
        for dev in mic_candidates[api_name]:
            mic_device = dev.index
            break
        if mic_device is not None:
            break

    # Fallback: use system default input if no mic found by name
    if mic_device is None:
        try:
            default_input = sd.query_devices(kind="input")
            if default_input and default_input["max_input_channels"] > 0:
                # Find the index
                for i, dev in enumerate(sd.query_devices()):
                    if dev["name"] == default_input["name"]:
                        mic_device = i
                        break
        except Exception:
            pass

    # --- Find loopback device ---
    loopback_device = None

    # Loopback devices are typically WDM-KS (Stereo Mix) or explicit loopback
    # Priority: WDM-KS Stereo Mix > any API with loopback keyword
    loopback_candidates: list[tuple[int, AudioDevice]] = []  # (priority, device)

    for dev in all_devices:
        if dev.max_input_channels > 0 and _is_loopback_device(dev.name):
            # Assign priority (lower is better)
            if "WDM-KS" in dev.hostapi_name:
                priority = 0  # WDM-KS is best for Stereo Mix
            elif "WASAPI" in dev.hostapi_name:
                priority = 1
            else:
                priority = 2
            loopback_candidates.append((priority, dev))

    # Sort by priority and pick best
    loopback_candidates.sort(key=lambda x: x[0])
    if loopback_candidates:
        loopback_device = loopback_candidates[0][1].index

    return mic_device, loopback_device


def find_best_devices(
    sample_rate: int = 16000, validate: bool = True
) -> tuple[int | None, int | None, list[str]]:
    """Find the best microphone and loopback devices with optional validation.

    This is a more thorough version of find_default_devices that:
    1. Tests devices to ensure they can actually be opened
    2. Returns warnings/suggestions for the user

    Args:
        sample_rate: Sample rate to test with
        validate: If True, test that devices can actually be opened

    Returns:
        Tuple of (mic_device_index, loopback_device_index, warnings)
        warnings is a list of user-friendly messages about issues found
    """
    require_recorder()

    warnings: list[str] = []
    all_devices = list_devices()

    # --- Find and validate microphone ---
    mic_device = None
    mic_candidates = [
        dev
        for dev in all_devices
        if dev.max_input_channels > 0 and _is_microphone_device(dev.name)
    ]

    # Sort by API preference (WASAPI > DirectSound > others)
    def mic_sort_key(dev: AudioDevice) -> int:
        if "WASAPI" in dev.hostapi_name:
            return 0
        elif "DirectSound" in dev.hostapi_name:
            return 1
        elif "MME" in dev.hostapi_name:
            return 2
        return 3

    mic_candidates.sort(key=mic_sort_key)

    for dev in mic_candidates:
        if validate:
            channels = min(1, dev.max_input_channels)
            if test_device(dev.index, channels=channels, sample_rate=sample_rate):
                mic_device = dev.index
                break
            else:
                warnings.append(f"Mic '{dev.name}' failed to open, trying next...")
        else:
            mic_device = dev.index
            break

    if mic_device is None and mic_candidates:
        warnings.append("No working microphone found. Check audio permissions.")
    elif mic_device is None:
        warnings.append("No microphone detected. Connect a microphone and retry.")

    # --- Find and validate loopback ---
    loopback_device = None
    loopback_candidates = [
        dev
        for dev in all_devices
        if dev.max_input_channels > 0 and _is_loopback_device(dev.name)
    ]

    # Sort by preference (WDM-KS Stereo Mix is usually best)
    def loopback_sort_key(dev: AudioDevice) -> int:
        if "WDM-KS" in dev.hostapi_name:
            return 0
        elif "WASAPI" in dev.hostapi_name:
            return 1
        return 2

    loopback_candidates.sort(key=loopback_sort_key)

    for dev in loopback_candidates:
        if validate:
            channels = min(2, dev.max_input_channels)
            if test_device(dev.index, channels=channels, sample_rate=sample_rate):
                loopback_device = dev.index
                break
            else:
                warnings.append(
                    f"Loopback '{dev.name}' failed to open. "
                    "It may be disabled in Windows Sound settings."
                )
        else:
            loopback_device = dev.index
            break

    if loopback_device is None:
        warnings.append(
            "No system audio capture device found. "
            "Enable 'Stereo Mix' in Windows Sound settings > Recording devices."
        )

    return mic_device, loopback_device, warnings


def _process_stereo_chunk(mic_data: Any, loopback_data: Any, np: Any) -> Any:
    """Process mic and loopback data into a stereo chunk.

    Args:
        mic_data: Microphone audio data (mono or multi-channel)
        loopback_data: Loopback audio data (stereo or mono)
        np: numpy module

    Returns:
        Stereo numpy array with mic on left, loopback on right
    """
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
    left_channel = mic_data[:, 0] if mic_data.ndim > 1 else mic_data.flatten()

    # Loopback stereo -> mix to mono for right channel
    if loopback_data.ndim > 1 and loopback_data.shape[1] >= 2:
        right_channel = (loopback_data[:, 0] + loopback_data[:, 1]) / 2
    else:
        right_channel = loopback_data.flatten()

    # Ensure same length after processing
    min_len = min(len(left_channel), len(right_channel))
    return np.column_stack([left_channel[:min_len], right_channel[:min_len]])


def _writer_thread(session: RecordingSession) -> None:
    """Background thread that periodically writes audio to disk.

    Streams are started in the main thread (required for WASAPI on Windows).
    This thread periodically flushes buffered data to disk to limit memory usage,
    then finalizes the file when stopped.
    """
    require_recorder()
    import numpy as np
    import soundfile as sf

    # Flush interval in seconds - write to disk every 5 seconds
    FLUSH_INTERVAL = 5.0

    sample_rate = session.sample_rate
    mode = session.mode

    # Determine channels and open output file for incremental writing
    if mode == RecordingMode.BOTH:
        channels = 2  # Stereo: mic on left, loopback on right
    elif mode == RecordingMode.SYSTEM_ONLY:
        channels = 2  # Loopback is typically stereo
    else:
        channels = 1  # Mic only is mono

    try:
        # Open file for incremental writing
        with sf.SoundFile(
            session.output_path,
            mode="w",
            samplerate=sample_rate,
            channels=channels,
            subtype="PCM_16",
        ) as outfile:
            last_flush = time.time()
            has_written_data = False

            # Periodically flush buffers to disk until stop signal
            while not session._stop_event.is_set():
                time.sleep(0.1)

                # Check if it's time to flush
                if time.time() - last_flush >= FLUSH_INTERVAL:
                    with session._buffer_lock:
                        mic_buffer = session._mic_buffer
                        loopback_buffer = session._loopback_buffer

                        if (
                            mode == RecordingMode.BOTH
                            and mic_buffer
                            and loopback_buffer
                        ):
                            # Process and write stereo data
                            mic_data = np.concatenate(mic_buffer, axis=0)
                            loopback_data = np.concatenate(loopback_buffer, axis=0)
                            stereo_data = _process_stereo_chunk(
                                mic_data, loopback_data, np
                            )
                            outfile.write(stereo_data)
                            has_written_data = True
                            # Clear buffers
                            session._mic_buffer.clear()
                            session._loopback_buffer.clear()

                        elif mode == RecordingMode.MIC_ONLY and mic_buffer:
                            mic_data = np.concatenate(mic_buffer, axis=0)
                            if mic_data.ndim > 1:
                                mic_data = mic_data[:, 0]
                            outfile.write(mic_data)
                            has_written_data = True
                            session._mic_buffer.clear()

                        elif mode == RecordingMode.SYSTEM_ONLY and loopback_buffer:
                            loopback_data = np.concatenate(loopback_buffer, axis=0)
                            outfile.write(loopback_data)
                            has_written_data = True
                            session._loopback_buffer.clear()

                    last_flush = time.time()

            # Stop signal received - stop and close streams
            if session._mic_stream is not None:
                session._mic_stream.stop()
                session._mic_stream.close()
            if session._loopback_stream is not None:
                session._loopback_stream.stop()
                session._loopback_stream.close()

            # Write any remaining buffered data
            with session._buffer_lock:
                mic_buffer = session._mic_buffer
                loopback_buffer = session._loopback_buffer

                if mode == RecordingMode.BOTH and mic_buffer and loopback_buffer:
                    mic_data = np.concatenate(mic_buffer, axis=0)
                    loopback_data = np.concatenate(loopback_buffer, axis=0)
                    stereo_data = _process_stereo_chunk(mic_data, loopback_data, np)
                    outfile.write(stereo_data)
                    has_written_data = True

                elif mode == RecordingMode.MIC_ONLY and mic_buffer:
                    mic_data = np.concatenate(mic_buffer, axis=0)
                    if mic_data.ndim > 1:
                        mic_data = mic_data[:, 0]
                    outfile.write(mic_data)
                    has_written_data = True

                elif mode == RecordingMode.SYSTEM_ONLY and loopback_buffer:
                    loopback_data = np.concatenate(loopback_buffer, axis=0)
                    outfile.write(loopback_data)
                    has_written_data = True

                # Handle edge case: BOTH mode but only one source had data
                elif mode == RecordingMode.BOTH:
                    if mic_buffer and not loopback_buffer:
                        mic_data = np.concatenate(mic_buffer, axis=0)
                        if mic_data.ndim > 1:
                            mic_data = mic_data[:, 0]
                        # Write as left channel only, right channel silent
                        stereo_data = np.column_stack(
                            [mic_data, np.zeros_like(mic_data)]
                        )
                        outfile.write(stereo_data)
                        has_written_data = True
                    elif loopback_buffer and not mic_buffer:
                        loopback_data = np.concatenate(loopback_buffer, axis=0)
                        if loopback_data.ndim > 1 and loopback_data.shape[1] >= 2:
                            right_channel = (
                                loopback_data[:, 0] + loopback_data[:, 1]
                            ) / 2
                        else:
                            right_channel = loopback_data.flatten()
                        # Write as right channel only, left channel silent
                        stereo_data = np.column_stack(
                            [np.zeros_like(right_channel), right_channel]
                        )
                        outfile.write(stereo_data)
                        has_written_data = True

            if not has_written_data:
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
        # Check if this is actually an input device
        if mic_info["max_input_channels"] == 0:
            raise ValueError(
                f"Device '{mic_info['name']}' cannot capture audio (no input channels). "
                "Use 'nb record devices' to find a valid microphone device."
            )

        mic_channels = min(1, mic_info["max_input_channels"])
        mic_stream = sd.InputStream(
            device=mic_device,
            channels=mic_channels,
            samplerate=sample_rate,
            callback=mic_callback,
        )
        mic_stream.start()

    if use_loopback:
        loopback_info = sd.query_devices(loopback_device)
        # Check if this is actually an input device
        if loopback_info["max_input_channels"] == 0:
            raise ValueError(
                f"Device '{loopback_info['name']}' cannot capture audio (no input channels). "
                "Use 'nb record devices' to find a valid loopback device like 'Stereo Mix'."
            )

        loopback_channels = min(2, loopback_info["max_input_channels"])
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
