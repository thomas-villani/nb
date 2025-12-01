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

   linked_notes:
     - path: ~/docs/wiki
       alias: wiki
       notebook: "@wiki"
       recursive: true
       todo_exclude: false
       sync: true
     - path: ~/code/project/TODO.md
       alias: project
       notebook: "@project"
       sync: true

   embeddings:
     provider: ollama
     model: nomic-embed-text

   todo_views:
     - name: work-urgent
       filters:
         notebooks: [work]
         tag: urgent
         hide_later: true

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

Linked notes options
--------------------

.. list-table::
   :header-rows: 1

   * - Option
     - Description
   * - ``path``
     - Path to file or directory (required)
   * - ``alias``
     - Short name for the link
   * - ``notebook``
     - Virtual notebook name (default: ``@alias``)
   * - ``recursive``
     - Scan subdirectories (for directories)
   * - ``todo_exclude``
     - Hide todos from ``nb todo``
   * - ``sync``
     - Sync completions back to source file

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
   * - ``api_key``
     - API key (for OpenAI)

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
   nb config set embeddings.api_key sk-...

Notebook settings
^^^^^^^^^^^^^^^^^

.. code-block:: bash

   nb config set notebook.work.color blue
   nb config set notebook.projects.icon wrench
   nb config set notebook.daily.icon calendar
   nb config get notebook.work.color

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
