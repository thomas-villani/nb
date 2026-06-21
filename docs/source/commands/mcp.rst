MCP Memory Server
=================

The MCP memory server exposes your ``nb`` notes as portable, cross-tool memory
over the `Model Context Protocol <https://modelcontextprotocol.io>`_. MCP
clients (Claude Desktop, Claude Code, Cursor, …) can **recall** from and
**remember** into your notes, so context follows you between tools.

.. note::

   The server is completely optional and runs only when you start it. It uses
   stdio transport: the MCP client launches ``nb`` as a subprocess and talks to
   it over stdin/stdout.

Installation
------------

The server requires the ``fastmcp`` package:

.. code-block:: bash

   uv sync --extra mcp
   # or
   uv pip install fastmcp

Running the server
------------------

.. code-block:: bash

   nb serve --mcp                          # Serve over stdio
   nb serve --mcp --memory-notebook brain  # Write memories to the 'brain' notebook

A standalone ``nb-mcp`` console script is also installed; it is what MCP client
configurations launch.

**Options:**

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``--mcp``
     - Required flag to start the server (otherwise ``serve`` prints help)
   * - ``--memory-notebook NAME``
     - Notebook that ``remember()`` writes to (overrides config/env)
   * - ``--profile {memory,full}``
     - Tool profile (default: ``memory``)

Tools
-----

The ``memory`` profile exposes four tools to the connected client:

.. list-table::
   :header-rows: 1

   * - Tool
     - Description
   * - ``recall``
     - Hybrid-search your notes and return ranked passages with citations
   * - ``remember``
     - Append a timestamped, provenance-tagged memory to today's note in the
       memory notebook
   * - ``list_notebooks``
     - List notebooks with note counts; flags the memory sink
   * - ``read_note``
     - Read a full note by path or id (blocks ``.nb/`` internals; honors the
       readable-notebook allowlist)

Memories written by ``remember`` are tagged with provenance (source, client,
session) and reindexed inline, so they are immediately recallable.

Connecting a client
-------------------

Generate a ready-to-paste client configuration block:

.. code-block:: bash

   nb mcp print-config
   nb mcp print-config --client claude-desktop
   nb mcp print-config --name nb-memory --memory-notebook brain

This emits JSON like:

.. code-block:: json

   {
     "mcpServers": {
       "nb-memory": {
         "command": "nb-mcp",
         "args": ["--profile", "memory"],
         "env": {
           "NB_MCP_MEMORY_NOTEBOOK": "memory"
         }
       }
     }
   }

Add the block to your client's MCP configuration. Two environment variables are
honored: ``NB_MCP_MEMORY_NOTEBOOK`` (the memory sink) and ``NB_MCP_CLIENT`` (a
label recorded in memory provenance).

Audit log
---------

Agent writes are logged (best-effort) to ``.nb/mcp.log`` in your notes root:

.. code-block:: bash

   nb mcp log              # Show the most recent writes
   nb mcp log -n 50        # Show the last 50 lines
   nb mcp log -f           # Follow the log (Ctrl-C to stop)

Logging can be disabled with ``mcp.log_writes: false`` (see below).

Configuration
-------------

Settings live under the ``mcp`` key in ``config.yaml``. See
:doc:`../reference/configuration` for the full table. Common options:

.. code-block:: yaml

   mcp:
     memory_notebook: memory     # where remember() writes (default: memory)
     readable_notebooks: []      # [] => all notebooks are recallable
     recall_default_limit: 6     # passages returned by recall
     recall_recency_boost: 0.3   # bias recall toward recent notes (0-1)
     log_writes: true            # log agent writes to .nb/mcp.log

To restrict what the server can read, list the allowed notebooks explicitly:

.. code-block:: yaml

   mcp:
     readable_notebooks: [memory, work, projects]
