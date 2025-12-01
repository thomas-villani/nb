Recording Commands
==================

Commands for recording meetings and generating transcripts.

.. note::

   Recording requires optional dependencies. Install with:

   .. code-block:: bash

      uv sync --extra recorder

   You also need:

   - WASAPI-capable audio devices (Windows)
   - Deepgram API key (set ``DEEPGRAM_API_KEY`` environment variable)

nb record start
---------------

Start recording audio from microphone and system audio.

**Usage:** ``nb record start [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-N, --name NAME``
     - Name for the recording (default: "recording")
   * - ``-n, --notebook NAME``
     - Notebook to save transcript to (default: daily)
   * - ``--audio-only``
     - Skip transcription, only record audio
   * - ``--delete-audio``
     - Delete WAV file after successful transcription
   * - ``--mic-only``
     - Record microphone only (no system audio)
   * - ``--system-only``
     - Record system audio only (no microphone)
   * - ``--mic INDEX``
     - Microphone device index
   * - ``--loopback INDEX``
     - System audio (loopback) device index

**Examples:**

.. code-block:: bash

   nb record start                      # Quick recording (mic + system)
   nb record start --name standup       # Named recording
   nb record start -n work              # Save transcript to work notebook
   nb record start --audio-only         # Record without transcription
   nb record start --mic-only           # Record microphone only
   nb record start --system-only        # Record system audio only
   nb record start --delete-audio       # Delete WAV after transcription
   nb record start --mic 1 --loopback 3 # Specify audio devices

**Recording process:**

1. Audio is captured from microphone and/or system audio (configurable)
2. Saved as WAV file (stereo when both sources, mono otherwise)
3. Press Ctrl+C to stop recording
4. Automatically transcribes (unless ``--audio-only``)

nb record stop
--------------

Stop a background recording session.

.. note::

   Usually you'll just press Ctrl+C in the ``start`` command.

nb transcribe
-------------

Transcribe an existing audio file (top-level command, not under ``record``).

**Usage:** ``nb transcribe AUDIO_FILE [OPTIONS]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``AUDIO_FILE``
     - Path to an audio file (WAV, MP3, M4A, FLAC, OGG, etc.)

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-N, --name NAME``
     - Name for the transcript (default: filename)
   * - ``-n, --notebook NAME``
     - Notebook to save transcript to
   * - ``-s, --speakers MAPPING``
     - Speaker names (e.g., "0:Alice,1:Bob")
   * - ``-a, --attendees LIST``
     - Attendee list (e.g., "Alice,Bob,Charlie")
   * - ``--copy``
     - Copy audio file to .nb/recordings/

**Examples:**

.. code-block:: bash

   nb transcribe ~/Downloads/meeting.wav
   nb transcribe meeting.mp3 --name client-call
   nb transcribe recording.wav -n work --speakers "0:Me,1:Client"
   nb transcribe meeting.wav --copy   # Also copy to .nb/recordings/

This command is useful when you have audio files from other sources
(phone recordings, downloaded meetings, etc.) that you want to transcribe
and add to your notes.

nb record transcribe
--------------------

Transcribe a recording using Deepgram API.

**Usage:** ``nb record transcribe [RECORDING_ID] [OPTIONS]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``RECORDING_ID``
     - Recording name (e.g., "2025-12-01_standup")

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Notebook to save transcript to
   * - ``-s, --speakers MAPPING``
     - Speaker names (e.g., "0:Alice,1:Bob")
   * - ``-a, --attendees LIST``
     - Attendee list (e.g., "Alice,Bob,Charlie")
   * - ``--all``
     - Transcribe all pending recordings
   * - ``--delete-audio``
     - Delete WAV file after successful transcription

**Examples:**

.. code-block:: bash

   nb record transcribe 2025-12-01_standup
   nb record transcribe 2025-12-01_standup --speakers "0:Me,1:Client"
   nb record transcribe --all
   nb record transcribe --all --delete-audio  # Transcribe and clean up

**Output files:**

- ``.nb/recordings/{id}.json`` - Structured transcript data
- ``{notebook}/{id}.md`` - Human-readable Markdown transcript

nb record list
--------------

List recordings with their transcription status.

**Usage:** ``nb record list [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--status [pending|transcribed|all]``
     - Filter by transcription status (default: all)

**Examples:**

.. code-block:: bash

   nb record list                    # All recordings
   nb record list --status pending   # Only untranscribed
   nb record list --status transcribed

nb record devices
-----------------

List available audio devices for recording.

**Usage:** ``nb record devices``

Shows input devices (microphones) and output devices that can be used
for system audio loopback (WASAPI).

Use the device index with ``--mic`` and ``--loopback`` options in
``nb record start``.

nb record purge
---------------

Delete old audio recordings to free up disk space.

**Usage:** ``nb record purge [OPTIONS]``

By default, only deletes transcribed recordings (those with a .json file).
The JSON transcript files are preserved.

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--transcribed``
     - Delete only transcribed recordings (have JSON)
   * - ``--all``
     - Delete all recordings (including pending)
   * - ``--older-than DAYS``
     - Delete recordings older than N days
   * - ``--dry-run``
     - Show what would be deleted without deleting

**Examples:**

.. code-block:: bash

   nb record purge                    # Delete transcribed WAV files
   nb record purge --older-than 30    # Delete transcribed older than 30 days
   nb record purge --all              # Delete all WAV files (including pending)
   nb record purge --dry-run          # Show what would be deleted

Transcript Format
-----------------

Transcripts are saved as Markdown with YAML frontmatter:

.. code-block:: markdown

   ---
   date: 2025-12-01
   tags: [meeting, transcript]
   duration: 30:45
   ---

   # Meeting: Standup

   **Date:** 2025-12-01 09:00
   **Duration:** 30:45

   ---

   **Speaker 0** [0:00]: Good morning everyone, let's start.

   **Speaker 1** [0:05]: Sure. Yesterday I worked on the API...

Speaker labels can be customized with the ``--speakers`` option during
transcription.

Command Alias
-------------

The ``rec`` alias can be used instead of ``record``:

.. code-block:: bash

   nb rec start --name meeting
   nb rec list
   nb rec transcribe 2025-12-01_meeting

Configuration
-------------

Recording settings can be configured in ``config.yaml``:

.. code-block:: yaml

   recorder:
     mic_device: 1              # Microphone device index (null for default)
     loopback_device: 3         # System audio device index (null for default)
     sample_rate: 16000         # Sample rate in Hz (16000 recommended for speech)
     auto_delete_audio: false   # Automatically delete WAV after transcription

Use ``nb record devices`` to find device indices for your system.
