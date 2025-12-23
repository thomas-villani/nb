Search Commands
===============

Commands for searching notes and todos.

nb search
---------

Search notes using keyword, semantic, or hybrid search.

**Usage:** ``nb search [OPTIONS] QUERY``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``QUERY``
     - Search query text

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-i, --interactive``
     - Launch interactive search TUI with live filtering
   * - ``-s, --semantic``
     - Semantic search only (find conceptually related content)
   * - ``-k, --keyword``
     - Keyword search only (exact matching)
   * - ``-t, --tag TAG``
     - Filter by tag
   * - ``-n, --notebook NAME``
     - Filter by notebook
   * - ``--when RANGE``
     - Date range (e.g., "last 2 weeks")
   * - ``--since DATE``
     - From a date onwards
   * - ``--until DATE``
     - Up to a date
   * - ``--recent``
     - Boost recent results in ranking
   * - ``--limit N``
     - Limit number of results
   * - ``-l, --files-only``
     - Only output file paths (no content/metadata)

Hybrid search (default) combines semantic similarity (70%) with keyword matching (30%) for best results.

.. image:: /_static/examples/search.svg
   :alt: nb search output
   :width: 80%

**Examples:**

.. code-block:: bash

   nb search "query"                    # Hybrid search (default)
   nb search -i                         # Interactive TUI
   nb search -i "project ideas"         # TUI with initial query
   nb search -s "query"                 # Semantic search only
   nb search -k "query"                 # Keyword search only
   nb search "query" -t mytag           # Filter by tag
   nb search "query" -n daily           # Filter by notebook
   nb search "query" --when "last 2 weeks"
   nb search "query" --since friday
   nb search "query" --recent --limit 5
   nb search "query" -l                 # Output file paths only

Interactive search TUI
^^^^^^^^^^^^^^^^^^^^^^

Launch an interactive search interface with live filtering and note preview:

.. code-block:: bash

   nb search -i                         # Open interactive search
   nb search -i "initial query"         # Start with a query
   nb search -i -n work                 # Filter to specific notebook
   nb search -i -t project              # Filter to specific tag

**Features:**

- Real-time search as you type
- Filter by notebook and tag using dropdowns
- Toggle recency boost for results
- Live preview of selected note content
- Open notes directly in editor
- Stream browse selected results

**Keyboard shortcuts:**

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Key
     - Action
   * - ``Enter``
     - Execute search / open selected note
   * - ``↑/↓``
     - Navigate results
   * - ``Tab``
     - Cycle focus between panels
   * - ``e``
     - Edit selected note in editor
   * - ``b``
     - Browse selected note in stream view
   * - ``q`` / ``Escape``
     - Quit

nb grep
-------

Search notes with regex pattern matching.

**Usage:** ``nb grep [OPTIONS] PATTERN``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``PATTERN``
     - Regular expression pattern

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Filter by notebook
   * - ``--note, -N NAME``
     - Filter by specific note
   * - ``-C N``
     - Show N lines of context (before and after)
   * - ``-B N``
     - Show N lines before match
   * - ``-A N``
     - Show N lines after match
   * - ``-l, --files-only``
     - Only output file paths with matches (no content)

**Examples:**

.. code-block:: bash

   nb grep "pattern"
   nb grep "TODO.*urgent"          # Regex patterns
   nb grep "config" -n work        # Filter by notebook
   nb grep "setup" --note myproject
   nb grep "pattern" -C 5          # 5 lines context
   nb grep "pattern" -l            # Output file paths only

Search tips
-----------

Semantic search
^^^^^^^^^^^^^^^

Use semantic search (``-s``) when you want to find conceptually related content, even if the exact words don't match:

.. code-block:: bash

   # Find notes about improving speed, even if they say
   # "optimization" or "performance" instead
   nb search -s "how to make things faster"

Keyword search
^^^^^^^^^^^^^^

Use keyword search (``-k``) when you need exact matches:

.. code-block:: bash

   # Find exact function name
   nb search -k "processUserInput"

Grep patterns
^^^^^^^^^^^^^

Use grep for complex patterns:

.. code-block:: bash

   # Find TODO comments with dates
   nb grep "TODO.*202[4-5]"

   # Find markdown headers
   nb grep "^## "

Command aliases
---------------

.. list-table::
   :header-rows: 1

   * - Alias
     - Command
   * - ``s``
     - ``search``
   * - ``ss``
     - ``search --semantic``
