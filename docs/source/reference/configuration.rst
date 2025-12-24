Configuration
=============

Configuration is stored in ``~/notes/.nb/config.yaml``.

Configuration file
------------------

Full example:

.. code-block:: yaml

   notes_root: ~/notes
   editor: micro

   notebooks:
     - name: daily
       date_based: true
       icon: calendar
     - name: projects
       date_based: false
       color: cyan
       icon: wrench
     - name: work
       date_based: true
       color: blue
     - name: personal
       date_based: false
       todo_exclude: true
       color: green
     - name: obsidian
       path: ~/Documents/Obsidian/vault
       date_based: false

   # Note: linked_notes are managed via 'nb link' command and stored in the database
   # The example below is for illustration only - use 'nb link add' to add links

   date_format: "%Y-%m-%d"
   time_format: "%H:%M"
   daily_title_format: "%A, %B %d, %Y"  # e.g., "Friday, November 28, 2025"
   week_start_day: monday  # monday or sunday

   embeddings:
     provider: ollama
     model: nomic-embed-text
     chunk_size: 500
     chunking_method: paragraphs  # sentences, tokens, paragraphs, sections

   search:
     vector_weight: 0.7      # 0=keyword only, 1=vector only
     score_threshold: 0.4    # Minimum score to show results
     recency_decay_days: 30  # Half-life for recency boost

   todo:
     default_sort: source    # source, tag, priority, created
     inbox_file: todo.md     # Name of inbox file in notes_root
     auto_complete_children: true  # Complete subtasks when parent is done

   recorder:
     mic_device: null
     loopback_device: null
     sample_rate: 16000
     auto_delete_audio: false
     transcribe_timeout: 600
     mic_speaker_label: "You"

   kanban_boards:
     - name: default
       columns:
         - name: Backlog
           filters: { status: pending, no_due_date: true }
           color: cyan
         - name: In Progress
           filters: { status: in_progress }
           color: green
         - name: Due Today
           filters: { due_today: true, status: pending }
           color: yellow
         - name: Done
           filters: { status: completed }
           color: dim

   todo_views:
     - name: work-urgent
       filters:
         notebooks: [work]
         tag: urgent
         hide_later: true

   git:
     enabled: false
     auto_commit: true
     commit_message_template: "Update {path}"

   # Custom .env file for API keys (optional, default: .nb/.env)
   # env_file: ~/secrets/nb.env

   llm:
     provider: anthropic
     models:
       smart: claude-sonnet-4-20250514
       fast: claude-haiku-3-5-20241022
     max_tokens: 4096
     temperature: 0.7

Notebook options
----------------

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``name``
     - Notebook name (required)
   * - ``date_based``
     - Use week-based date organization
   * - ``todo_exclude``
     - Exclude from ``nb todo`` by default
   * - ``path``
     - External directory path
   * - ``color``
     - Display color (blue, green, cyan, magenta, #ff5500)
   * - ``icon``
     - Display icon/emoji prefix
   * - ``template``
     - Default template name for new notes

Icon aliases
^^^^^^^^^^^^

Use emoji directly or these aliases:

``calendar``, ``note``, ``book``, ``wrench``, ``hammer``, ``gear``,
``star``, ``check``, ``pin``, ``flag``, ``work``, ``home``, ``code``,
``rocket``, ``target``, ``brain``

Linked notes
------------

Linked notes are **stored in the database**, not in config.yaml. Use the ``nb link`` command to manage them:

.. code-block:: bash

   nb link add ~/docs/wiki --alias wiki          # Link a directory
   nb link add ~/code/TODO.md --alias project    # Link a file
   nb link list                                   # List all links
   nb link remove wiki                            # Remove a link

**Link options** (specified via command flags):

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``--alias, -a``
     - Short name for the link
   * - ``--notebook, -n``
     - Virtual notebook name (default: ``@alias``)
   * - ``--recursive / --no-recursive``
     - Scan subdirectories (for directories)
   * - ``--todo-exclude``
     - Hide todos from ``nb todo``
   * - ``--sync / --no-sync``
     - Sync completions back to source file

See :doc:`../commands/linked-files` for full documentation.

Global options
--------------

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``notes_root``
     - Root directory for all notes
   * - ``editor``
     - Text editor command (e.g., ``vim``, ``code``)
   * - ``date_format``
     - Date display format (default: ``%Y-%m-%d``)
   * - ``time_format``
     - Time display format (default: ``%H:%M``)
   * - ``daily_title_format``
     - Format for daily note titles (default: ``%A, %B %d, %Y``)
   * - ``week_start_day``
     - First day of week: ``monday`` or ``sunday``

Embeddings options
------------------

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``provider``
     - ``ollama`` or ``openai``
   * - ``model``
     - Model name (e.g., ``nomic-embed-text``)
   * - ``base_url``
     - Custom endpoint URL
   * - ``chunk_size``
     - Max tokens per chunk (default: 500)
   * - ``chunking_method``
     - ``sentences``, ``tokens``, ``paragraphs``, or ``sections``

**Note:** When using ``openai`` provider, set the ``OPENAI_API_KEY`` environment variable.

Search options
--------------

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``vector_weight``
     - Hybrid search ratio (0=keyword only, 1=vector only, default: 0.7)
   * - ``score_threshold``
     - Minimum score to show results (default: 0.4)
   * - ``recency_decay_days``
     - Half-life for recency boost (default: 30)

Todo options
------------

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``default_sort``
     - Default sort order: ``source``, ``tag``, ``priority``, ``created``
   * - ``inbox_file``
     - Name of inbox file in notes_root (default: ``todo.md``)
   * - ``auto_complete_children``
     - Complete subtasks when parent is done (default: true)

Recorder options
----------------

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``mic_device``
     - Microphone device index (null for default)
   * - ``loopback_device``
     - System audio device index (null for default)
   * - ``sample_rate``
     - Sample rate in Hz (16000 for MME, 48000 for WASAPI)
   * - ``auto_delete_audio``
     - Delete WAV after successful transcription
   * - ``transcribe_timeout``
     - Deepgram API timeout in seconds (default: 600)
   * - ``mic_speaker_label``
     - Label for microphone speaker in transcripts (default: "You")

Git options
-----------

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``enabled``
     - Enable git integration (default: false)
   * - ``auto_commit``
     - Auto-commit after note changes (default: true)
   * - ``commit_message_template``
     - Commit message template (default: "Update {path}")

Template variables: ``{path}``, ``{notebook}``, ``{title}``, ``{date}``

LLM options
-----------

Configure AI features for ``nb ask`` and other AI-powered commands.

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``provider``
     - LLM provider: ``anthropic`` or ``openai``
   * - ``models.smart``
     - Model for quality answers (default: ``claude-sonnet-4-20250514``)
   * - ``models.fast``
     - Model for quick answers (default: ``claude-haiku-3-5-20241022``)
   * - ``base_url``
     - Custom API endpoint URL
   * - ``max_tokens``
     - Maximum tokens in response (default: 4096)
   * - ``temperature``
     - Response randomness 0-1 (default: 0.7)
   * - ``system_prompt``
     - Custom system prompt for all AI commands

**API keys:** Set the appropriate environment variable based on provider:

- ``ANTHROPIC_API_KEY`` - for Anthropic Claude models
- ``OPENAI_API_KEY`` - for OpenAI GPT models

See :ref:`api-keys` for details on configuring API keys.

**Example configuration:**

.. code-block:: yaml

   llm:
     provider: anthropic
     models:
       smart: claude-sonnet-4-20250514
       fast: claude-haiku-3-5-20241022
     max_tokens: 4096
     temperature: 0.7
     system_prompt: |
       You are a helpful assistant for managing notes and productivity.

**Configure via CLI:**

.. code-block:: bash

   nb config set llm.provider anthropic
   nb config set llm.models.smart claude-sonnet-4-20250514
   nb config set llm.models.fast claude-haiku-3-5-20241022
   nb config set llm.max_tokens 4096
   nb config set llm.temperature 0.7

Kanban board options
--------------------

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``name``
     - Board name
   * - ``columns``
     - List of column definitions

**Column options:**

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``name``
     - Column display name
   * - ``filters``
     - Filter criteria (see below)
   * - ``color``
     - Display color

**Available column filters:**

- ``status``: ``pending``, ``in_progress``, or ``completed``
- ``due_today``: true - todos due today
- ``due_this_week``: true - todos due within 7 days
- ``overdue``: true - past due, not completed
- ``no_due_date``: true - todos without a due date
- ``priority``: 1, 2, or 3
- ``tags``: list of tags to filter by

Todo view options
-----------------

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``name``
     - View name
   * - ``filters``
     - Filter criteria

**Available view filters:**

- ``notebooks``: list of notebook names
- ``notes``: list of note paths
- ``tag``: single tag to filter by
- ``priority``: 1, 2, or 3
- ``exclude_tags``: list of tags to exclude
- ``hide_later``: hide "DUE LATER" section
- ``hide_no_date``: hide "NO DUE DATE" section
- ``include_completed``: include completed todos

Configuration commands
----------------------

Open config file
^^^^^^^^^^^^^^^^

.. code-block:: bash

   nb config

Get/set values
^^^^^^^^^^^^^^

.. code-block:: bash

   nb config get editor
   nb config set editor vim
   nb config set date_format "%Y-%m-%d"
   nb config set time_format "%H:%M"

Embeddings settings
^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   nb config set embeddings.provider ollama
   nb config set embeddings.model nomic-embed-text
   nb config set embeddings.base_url http://localhost:11434

Notebook settings
^^^^^^^^^^^^^^^^^

.. code-block:: bash

   nb config set notebook.work.color blue
   nb config set notebook.projects.icon wrench
   nb config set notebook.daily.icon calendar
   nb config get notebook.work.color

Git settings
^^^^^^^^^^^^

.. code-block:: bash

   nb config set git.enabled true
   nb config set git.auto_commit false
   nb config set git.commit_message_template "nb: {path}"

Todo exclusion
^^^^^^^^^^^^^^

.. code-block:: bash

   nb config exclude personal              # Exclude notebook
   nb config include personal              # Include notebook
   nb config exclude projects/old-idea     # Exclude note
   nb config include projects/old-idea     # Include note

List settings
^^^^^^^^^^^^^

.. code-block:: bash

   nb config list

.. _api-keys:

API Keys
--------

API keys are **never stored in config.yaml** (which may be committed to version control).
They are loaded exclusively from environment variables.

**Priority order** (first found wins):

1. Shell environment variables (already set in your terminal)
2. Custom ``.env`` file (if ``env_file`` is set in config.yaml)
3. Default ``.nb/.env`` file in notes_root

**Supported API keys:**

.. list-table::
   :header-rows: 1

   * - Variable
     - Service
     - Used By
   * - ``ANTHROPIC_API_KEY``
     - LLM (Claude)
     - AI commands (``nb ask``, ``nb assistant``, etc.) when ``llm.provider: anthropic``
   * - ``OPENAI_API_KEY``
     - LLM / Embeddings
     - AI commands when ``llm.provider: openai``, embeddings when ``embeddings.provider: openai``
   * - ``SERPER_API_KEY``
     - Web Search
     - ``nb research`` command
   * - ``DEEPGRAM_API_KEY``
     - Transcription
     - ``nb transcribe`` command
   * - ``RAINDROP_API_KEY``
     - Inbox
     - ``nb inbox`` command

**Setting up API keys:**

Create a ``.env`` file in your notes root:

.. code-block:: bash

   # Create .env file
   nano ~/notes/.nb/.env

Example ``.env`` file:

.. code-block:: text

   ANTHROPIC_API_KEY=sk-ant-api...
   DEEPGRAM_API_KEY=...
   SERPER_API_KEY=...
   RAINDROP_API_KEY=...

**Using a custom .env file:**

.. code-block:: bash

   nb config set env_file ~/secrets/nb.env

**View detected API keys:**

.. code-block:: bash

   nb config api-keys

This shows which API keys are detected and their sources (masked for security).

Environment variables
---------------------

.. list-table::
   :header-rows: 1

   * - Variable
     - Description
   * - ``NB_NOTES_ROOT``
     - Override notes root directory
   * - ``EDITOR``
     - Default editor
   * - ``ANTHROPIC_API_KEY``
     - API key for Anthropic Claude models
   * - ``OPENAI_API_KEY``
     - API key for OpenAI GPT models / embeddings
   * - ``SERPER_API_KEY``
     - API key for Serper web search
   * - ``DEEPGRAM_API_KEY``
     - API key for Deepgram transcription
   * - ``RAINDROP_API_KEY``
     - API key for Raindrop.io inbox integration
