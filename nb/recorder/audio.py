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

from nb.recorder import is_wasapi_loopback_available, require_recorder

if TYPE_CHECKING:
    pass

# Peak-normalization targets applied when finalizing a recording.
# The reference level is a high percentile rather than the true peak so a
# handful of USB glitch samples can't defeat the gain calculation (a real
# capture measured peak=1.0 from 31 stray samples while p99.9 was only 0.179 —
# peak-normalizing would have made it *quieter*).
_NORM_PERCENTILE = 99.9
_NORM_TARGET = 0.5  # -6 dBFS for the reference percentile
_NORM_MAX_GAIN = 20.0  # don't amplify near-silence into full-scale hiss
_SILENT_RMS = 1e-4  # below this a channel is treated as dead, not quiet

# How often the loopback worker checks whether Windows switched output devices
_DEVICE_POLL_INTERVAL = 1.0


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
    # How system audio is being captured: "wasapi-loopback", "stereo-mix", "none"
    loopback_method: str = "none"
    loopback_name: str | None = None
    # Why WASAPI loopback wasn't used, when it was tried and failed
    loopback_fallback_reason: str | None = None
    # Frames of system audio the loopback capture couldn't keep up with
    loopback_dropped_frames: int = 0
    # Times the Windows default output changed mid-recording (headphones in/out)
    loopback_switches: int = 0
    # Per-channel levels/gains from the normalization pass (set by stop_recording)
    level_stats: list = field(default_factory=list)
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _error: Exception | None = None
    _started: threading.Event = field(default_factory=threading.Event)
    # Stream and buffer references (set by start_recording)
    _mic_stream: Any = None  # sd.InputStream
    _loopback_stream: Any = None  # sd.InputStream
    _loopback_thread: threading.Thread | None = None
    _loopback_ready: threading.Event = field(default_factory=threading.Event)
    _loopback_error: Exception | None = None
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


def _wasapi_extra_settings(device_index: int | None) -> Any:
    """Return WASAPI settings enabling sample-rate conversion, else None.

    WASAPI shared mode only accepts the device's native mix rate (48 kHz on
    most hardware). Without `auto_convert` every WASAPI mic fails to open at
    the recorder's default 16 kHz, and device detection silently falls all the
    way through to the DirectSound/MME backends.
    """
    import sounddevice as sd

    if device_index is None:
        return None
    try:
        hostapi_idx = sd.query_devices(device_index)["hostapi"]
        if "WASAPI" in sd.query_hostapis()[hostapi_idx]["name"]:
            return sd.WasapiSettings(auto_convert=True)
    except Exception:
        pass
    return None


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


def _validate_configured_mic(device_index: int) -> int | None:
    """Drop a configured mic_device if it's actually a loopback/system-audio source.

    Returning None lets the caller fall back to auto-detection, so a stale config
    value (e.g. Stereo Mix saved as mic_device) can't silently make both channels
    of a stereo recording capture the same system audio.
    """
    import sys

    import sounddevice as sd

    try:
        info = sd.query_devices(device_index)
    except Exception:
        return None

    name = info["name"]
    if _is_loopback_device(name):
        print(
            f"Warning: mic_device [{device_index}] '{name}' is a system-audio "
            "loopback, not a microphone. Ignoring and auto-detecting instead.",
            file=sys.stderr,
        )
        return None
    return device_index


def _validate_configured_loopback(device_index: int) -> int | None:
    """Drop a configured loopback_device if it's clearly a physical microphone."""
    import sys

    import sounddevice as sd

    try:
        info = sd.query_devices(device_index)
    except Exception:
        return None

    name = info["name"]
    if _is_microphone_device(name):
        print(
            f"Warning: loopback_device [{device_index}] '{name}' looks like a "
            "microphone, not a system-audio source. Ignoring and auto-detecting instead.",
            file=sys.stderr,
        )
        return None
    return device_index


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
        # Use callback mode to match how start_recording() opens streams.
        # Some Windows audio backends (e.g. WDM-KS) may accept blocking mode
        # but reject callback mode with paInvalidDevice (-9996).
        def _noop_callback(indata, frames, time_info, status):
            pass

        stream = sd.InputStream(
            device=device_index,
            channels=channels,
            samplerate=sample_rate,
            callback=_noop_callback,
            extra_settings=_wasapi_extra_settings(device_index),
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


def get_default_output_name() -> str | None:
    """Name of the Windows default output device, or None if unavailable.

    This is the device WASAPI loopback captures from — headphones, Bluetooth,
    or onboard speakers, whichever Windows is currently using.
    """
    if not is_wasapi_loopback_available():
        return None
    try:
        import soundcard as sc

        return str(sc.default_speaker().name)
    except Exception:
        return None


def _init_com_for_thread() -> bool:
    """Initialize COM (multithreaded apartment) for the calling thread.

    `soundcard` initializes COM once, on whichever thread imported it. PortAudio
    calls `CoUninitialize()` when it tears down streams — which device detection
    does a lot of — dropping that refcount to zero and leaving every later
    soundcard call failing with CO_E_NOTINITIALIZED (0x800401f0). COM apartments
    are per-thread, so initializing here makes the loopback worker immune to
    whatever PortAudio does on the main thread.

    Returns True if this call initialized COM and must balance it later.
    """
    import ctypes

    COINIT_MULTITHREADED = 0x0
    S_OK, S_FALSE = 0x0, 0x1
    RPC_E_CHANGED_MODE = -0x7FFEFEFA  # 0x80010106 as a signed HRESULT

    hr = ctypes.windll.ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
    if hr == RPC_E_CHANGED_MODE:
        # Thread is already in a different apartment; usable, don't uninitialize.
        return False
    return hr in (S_OK, S_FALSE)


def _wasapi_loopback_worker(session: RecordingSession) -> None:
    """Capture system audio via WASAPI loopback until the session stops.

    Unlike the sounddevice streams (callback-driven), `soundcard`'s recorder is
    a blocking pull API, so this runs on its own thread and appends into the
    same buffer the writer thread drains.
    """
    com_owned = _init_com_for_thread()

    import warnings

    import soundcard as sc

    # soundcard warns per dropped block ("data discontinuity in recording") and
    # forces the warning to always display, which spams the recording UI. Track
    # the shortfall in frames instead and report it once at the end — that says
    # how much audio was actually lost, which the warning count doesn't.
    warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)

    sample_rate = session.sample_rate
    # ~100 ms per read: small enough to stop promptly, large enough that the
    # WASAPI buffer isn't starved by scheduling jitter.
    chunk = max(256, sample_rate // 10)

    started = time.time()
    frames = 0

    opened_once = False

    try:
        # Re-bind whenever Windows changes the default output. A loopback client
        # is tied to one endpoint, so plugging in headphones mid-meeting would
        # otherwise leave us capturing an idle device — silence for the rest of
        # the recording, which is the exact bug this whole path exists to fix.
        while not session._stop_event.is_set():
            try:
                speaker = sc.default_speaker()
                device_id = str(speaker.id)
                loop_mic = sc.get_microphone(id=device_id, include_loopback=True)

                with loop_mic.recorder(
                    samplerate=sample_rate, channels=2, blocksize=chunk
                ) as rec:
                    session.loopback_name = str(speaker.name)
                    opened_once = True
                    session._loopback_ready.set()
                    last_check = time.time()

                    while not session._stop_event.is_set():
                        data = rec.record(numframes=chunk)
                        frames += len(data)
                        with session._buffer_lock:
                            session._loopback_buffer.append(data)

                        # Polling the default device is a COM round-trip, so
                        # keep it off the per-chunk path.
                        if time.time() - last_check >= _DEVICE_POLL_INTERVAL:
                            last_check = time.time()
                            try:
                                if str(sc.default_speaker().id) != device_id:
                                    session.loopback_switches += 1
                                    break  # reopen against the new default
                            except Exception:
                                pass  # transient enumeration blip; keep going
            except Exception:
                # Failing to open the very first time is fatal — the caller
                # falls back to Stereo Mix. After that it's a device being
                # swapped out from under us: back off and re-bind rather than
                # abandoning the rest of the recording.
                if not opened_once:
                    raise
                session._stop_event.wait(timeout=0.3)

        elapsed = time.time() - started
        expected = int(elapsed * sample_rate)
        session.loopback_dropped_frames = max(0, expected - frames)
    except Exception as e:
        session._loopback_error = e
        session._loopback_ready.set()
    finally:
        if com_owned:
            import ctypes

            ctypes.windll.ole32.CoUninitialize()


def _start_wasapi_loopback(session: RecordingSession) -> bool:
    """Try to start WASAPI loopback capture. Returns True on success.

    Falls back to the caller's Stereo Mix path if loopback can't be opened.
    """
    if not is_wasapi_loopback_available():
        return False

    thread = threading.Thread(
        target=_wasapi_loopback_worker, args=(session,), daemon=True
    )
    thread.start()

    # Wait for the recorder to actually open so a failure falls back cleanly
    # instead of yielding a silent right channel.
    if not session._loopback_ready.wait(timeout=5.0):
        session._stop_event.set()
        thread.join(timeout=2.0)
        session._stop_event.clear()
        session.loopback_fallback_reason = "WASAPI loopback timed out while opening"
        return False

    if session._loopback_error is not None:
        thread.join(timeout=2.0)
        session.loopback_fallback_reason = str(session._loopback_error)
        session._loopback_error = None
        return False

    session._loopback_thread = thread
    session.loopback_method = "wasapi-loopback"
    return True


def _normalize_channel_gain(channel: Any, np: Any) -> tuple[float, float, bool]:
    """Compute a normalization gain for one channel.

    Returns (gain, rms, is_silent). Dead channels are left untouched — a truly
    silent source (e.g. Stereo Mix while playback is on headphones) would
    otherwise be amplified into full-scale hiss and wreck transcription.
    """
    rms = float(np.sqrt((channel.astype(np.float64) ** 2).mean()))
    if rms < _SILENT_RMS:
        return 1.0, rms, True

    reference = float(np.percentile(np.abs(channel), _NORM_PERCENTILE))
    if reference <= 0:
        return 1.0, rms, True

    gain = min(_NORM_TARGET / reference, _NORM_MAX_GAIN)
    return max(gain, 1.0), rms, False


def normalize_recording(path: Path) -> list[dict[str, Any]]:
    """Peak-normalize each channel of a finished recording, in place.

    Channels are scaled independently so a quiet mic isn't held back by a loud
    system-audio channel (or vice versa). Runs as a second pass over the
    finished WAV rather than during capture, so a crash mid-meeting still
    leaves a valid, recoverable file.

    Returns per-channel stats (pre-normalization rms, applied gain, silent).
    """
    require_recorder()
    import numpy as np
    import soundfile as sf

    data, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    if len(data) == 0:
        return []

    stats: list[dict[str, Any]] = []
    for c in range(data.shape[1]):
        gain, rms, silent = _normalize_channel_gain(data[:, c], np)
        stats.append({"channel": c, "rms": rms, "gain": gain, "silent": silent})
        if gain != 1.0:
            data[:, c] = np.clip(data[:, c] * gain, -1.0, 1.0)

    if any(s["gain"] != 1.0 for s in stats):
        tmp = path.with_suffix(".norm.wav")
        sf.write(tmp, data, sample_rate, subtype="PCM_16")
        tmp.replace(path)

    return stats


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


def _drain_buffers(session: RecordingSession) -> tuple[list, list]:
    """Take everything currently buffered, leaving the capture lists empty.

    Kept deliberately tiny: the capture threads block on this lock, so it must
    never be held across numpy concatenation or disk I/O.
    """
    with session._buffer_lock:
        mic_chunks = session._mic_buffer[:]
        loopback_chunks = session._loopback_buffer[:]
        session._mic_buffer.clear()
        session._loopback_buffer.clear()
    return mic_chunks, loopback_chunks


def _restore_buffers(
    session: RecordingSession, mic_chunks: list, loopback_chunks: list
) -> None:
    """Put drained chunks back at the front, preserving capture order."""
    with session._buffer_lock:
        session._mic_buffer[:0] = mic_chunks
        session._loopback_buffer[:0] = loopback_chunks


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
                    # Detach the buffers under the lock, then concatenate and
                    # write OUTSIDE it. Holding the lock across disk I/O stalls
                    # both capture threads for the duration of every write,
                    # overrunning the WASAPI buffer — which surfaces as
                    # "data discontinuity in recording" every flush interval.
                    mic_buffer, loopback_buffer = _drain_buffers(session)

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

                    elif mic_buffer or loopback_buffer:
                        # Nothing written this round (e.g. BOTH mode with only
                        # one source producing yet) — put the data back so it
                        # isn't dropped.
                        _restore_buffers(session, mic_buffer, loopback_buffer)

                    last_flush = time.time()

            # Stop signal received - stop and close streams
            if session._mic_stream is not None:
                session._mic_stream.stop()
                session._mic_stream.close()
            if session._loopback_stream is not None:
                session._loopback_stream.stop()
                session._loopback_stream.close()
            # The WASAPI loopback worker polls _stop_event; wait for its final
            # chunk so it isn't still appending while we drain the buffers.
            if session._loopback_thread is not None:
                session._loopback_thread.join(timeout=3.0)

            # Write any remaining buffered data. Capture has already stopped
            # here, but drain-then-process keeps the lock discipline uniform.
            mic_buffer, loopback_buffer = _drain_buffers(session)

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
                    stereo_data = np.column_stack([mic_data, np.zeros_like(mic_data)])
                    outfile.write(stereo_data)
                    has_written_data = True
                elif loopback_buffer and not mic_buffer:
                    loopback_data = np.concatenate(loopback_buffer, axis=0)
                    if loopback_data.ndim > 1 and loopback_data.shape[1] >= 2:
                        right_channel = (loopback_data[:, 0] + loopback_data[:, 1]) / 2
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

    # Drop stale/mis-typed device indices before resolving defaults.
    if mic_device is not None:
        mic_device = _validate_configured_mic(mic_device)
    if loopback_device is not None:
        loopback_device = _validate_configured_loopback(loopback_device)

    wants_system = mode in (RecordingMode.BOTH, RecordingMode.SYSTEM_ONLY)

    # Prefer WASAPI loopback for system audio: it captures whichever output
    # device Windows is currently using, so it keeps working when headphones
    # are plugged in. An explicit --loopback index opts back into Stereo Mix.
    try_wasapi_loopback = (
        wants_system and loopback_device is None and is_wasapi_loopback_available()
    )

    # Find validated defaults for any unspecified devices. Stereo Mix detection
    # is skipped when WASAPI loopback will be used — it opens and tests every
    # candidate device, which is slow and pointless here.
    need_stereo_mix = (
        wants_system and loopback_device is None and not try_wasapi_loopback
    )
    if mic_device is None or need_stereo_mix:
        default_mic, default_loopback, _warnings = find_best_devices(
            sample_rate=sample_rate, validate=True
        )
        if mode in (RecordingMode.BOTH, RecordingMode.MIC_ONLY) and mic_device is None:
            mic_device = default_mic
        if need_stereo_mix:
            loopback_device = default_loopback

    # Validate we have required devices
    if mode == RecordingMode.MIC_ONLY and mic_device is None:
        raise ValueError("No microphone device found. Use --mic to specify one.")
    if (
        mode == RecordingMode.SYSTEM_ONLY
        and loopback_device is None
        and not try_wasapi_loopback
    ):
        raise ValueError("No system audio device found. Use --loopback to specify one.")
    if (
        mode == RecordingMode.BOTH
        and mic_device is None
        and loopback_device is None
        and not try_wasapi_loopback
    ):
        raise ValueError(
            "No audio devices found. Use --mic and/or --loopback to specify."
        )

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine which streams to open based on mode
    use_mic = (
        mode in (RecordingMode.BOTH, RecordingMode.MIC_ONLY) and mic_device is not None
    )

    session = RecordingSession(
        output_path=output_path,
        mic_device=mic_device,
        loopback_device=loopback_device,
        sample_rate=sample_rate,
        mode=mode,
    )

    # Shared buffers for callbacks (owned by the session so the loopback
    # worker thread and the writer thread drain the same lists)
    mic_buffer: list = session._mic_buffer
    loopback_buffer: list = session._loopback_buffer
    buffer_lock = session._buffer_lock

    # Start WASAPI loopback before opening the Stereo Mix stream, so a failure
    # falls back rather than leaving system audio silently dead.
    if try_wasapi_loopback and _start_wasapi_loopback(session):
        loopback_device = None
        session.loopback_device = None
    elif try_wasapi_loopback:
        # Loopback unavailable at runtime — fall back to Stereo Mix detection
        _mic, default_loopback, _warnings = find_best_devices(
            sample_rate=sample_rate, validate=True
        )
        loopback_device = default_loopback
        session.loopback_device = default_loopback

    use_loopback = (
        session.loopback_method != "wasapi-loopback"
        and wants_system
        and loopback_device is not None
    )

    if (
        mode == RecordingMode.SYSTEM_ONLY
        and not use_loopback
        and not try_wasapi_loopback
    ):
        raise ValueError("No system audio device found. Use --loopback to specify one.")

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
        try:
            mic_stream = sd.InputStream(
                device=mic_device,
                channels=mic_channels,
                samplerate=sample_rate,
                callback=mic_callback,
                extra_settings=_wasapi_extra_settings(mic_device),
            )
            mic_stream.start()
        except Exception as e:
            raise ValueError(
                f"Cannot open microphone [{mic_device}] '{mic_info['name']}': {e}"
            ) from e

    if use_loopback:
        loopback_info = sd.query_devices(loopback_device)
        # Check if this is actually an input device
        if loopback_info["max_input_channels"] == 0:
            if mic_stream is not None:
                mic_stream.stop()
                mic_stream.close()
            raise ValueError(
                f"Device '{loopback_info['name']}' cannot capture audio (no input channels). "
                "Use 'nb record devices' to find a valid loopback device like 'Stereo Mix'."
            )

        loopback_channels = min(2, loopback_info["max_input_channels"])
        try:
            loopback_stream = sd.InputStream(
                device=loopback_device,
                channels=loopback_channels,
                samplerate=sample_rate,
                callback=loopback_callback,
                extra_settings=_wasapi_extra_settings(loopback_device),
            )
            loopback_stream.start()
        except Exception as e:
            if mic_stream is not None:
                mic_stream.stop()
                mic_stream.close()
            raise ValueError(
                f"Cannot open loopback [{loopback_device}] '{loopback_info['name']}': {e}"
            ) from e

    if (
        mic_stream is None
        and loopback_stream is None
        and session.loopback_method != "wasapi-loopback"
    ):
        raise ValueError("Failed to open any audio streams")

    # Store streams in session for the writer thread (buffers already shared)
    session._mic_stream = mic_stream
    session._loopback_stream = loopback_stream
    if loopback_stream is not None:
        session.loopback_method = "stereo-mix"
        try:
            session.loopback_name = str(sd.query_devices(loopback_device)["name"])
        except Exception:
            pass

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

    # Level-correct the finished file. Never fatal: a normalization failure
    # must not cost the user a recording that is already safely on disk.
    try:
        session.level_stats = normalize_recording(session.output_path)
    except Exception as e:
        import sys

        print(f"Warning: could not normalize levels: {e}", file=sys.stderr)

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
