Inbox Commands
==============

Pull bookmarks from Raindrop.io and clip them as notes.

The inbox feature connects to your Raindrop.io account to pull bookmarks from a designated collection and convert them into markdown notes using nb's web clipping functionality.

Setup
-----

1. **Get a Raindrop API token:**

   - Go to https://app.raindrop.io/settings/integrations
   - Click "Create new app" under "For Developers"
   - Name it something like "nb-cli"
   - Copy the "Test token"

2. **Set the environment variable:**

   .. code-block:: powershell

      # PowerShell (add to your profile for persistence)
      $env:RAINDROP_API_KEY = "your-token-here"

   .. code-block:: bash

      # Bash/Zsh
      export RAINDROP_API_KEY="your-token-here"

3. **Create an inbox collection in Raindrop** (default name: ``nb-inbox``)

4. **Optionally configure settings:**

   .. code-block:: bash

      nb config set inbox.raindrop.collection "my-inbox"
      nb config set inbox.default_notebook "reading"

nb inbox list
-------------

Show pending items from your Raindrop inbox collection.

Already-clipped items are hidden by default. Use ``--all`` to include them.

**Usage:** ``nb inbox list [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-l, --limit INTEGER``
     - Maximum items to show (default: 20)
   * - ``-c, --collection TEXT``
     - Raindrop collection name (overrides config)
   * - ``-a, --all``
     - Include already-clipped items

**Examples:**

.. code-block:: bash

   nb inbox list              # Show up to 20 pending items
   nb inbox list -l 50        # Show up to 50 items
   nb inbox list -c reading   # List from 'reading' collection
   nb inbox list --all        # Include already-clipped items

nb inbox pull
-------------

Pull and clip items from Raindrop inbox as markdown notes.

By default runs interactively, prompting for each item. Already-clipped items are hidden by default. Use ``--all`` to include them, or ``--auto`` to clip all items without prompting.

**Usage:** ``nb inbox pull [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook TEXT``
     - Notebook to clip items to (overrides collection mapping)
   * - ``--auto``
     - Clip all items without prompting
   * - ``-a, --all``
     - Include already-clipped items
   * - ``-l, --limit INTEGER``
     - Maximum items to process per collection (default: 10)
   * - ``-c, --collection TEXT``
     - Specific Raindrop collection (default: all configured)
   * - ``-t, --tag TEXT``
     - Additional tags (repeatable)
   * - ``--no-archive``
     - Don't archive items after clipping
   * - ``--ai / --no-ai``
     - Generate AI summary for clipped content (default: from config ``inbox.auto_summarize``)

**Interactive Mode Commands:**

When running without ``--auto``, you can use these commands at each prompt:

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Command
     - Action
   * - ``Enter``
     - Clip to default/specified notebook
   * - ``<name>``
     - Clip to different notebook
   * - ``s``
     - Skip this item
   * - ``d``
     - Mark as duplicate and skip
   * - ``q``
     - Quit processing
   * - ``?``
     - Show help

**Examples:**

.. code-block:: bash

   nb inbox pull                    # Interactive mode, all collections
   nb inbox pull --auto             # Clip all to configured notebooks
   nb inbox pull -n bookmarks       # Clip all to 'bookmarks' (override)
   nb inbox pull -c research        # Only process 'research' collection
   nb inbox pull -l 5               # Process only 5 items per collection
   nb inbox pull -t research        # Add #research tag to all
   nb inbox pull --all              # Include already-clipped items
   nb inbox pull --no-ai            # Disable AI summary generation

**Example Interactive Session:**

.. code-block:: text

   Inbox: 3 items pending

   1. How to Build a Second Brain (medium.com)
      Tags: #productivity #reading
      → Clip to [bookmarks]: _

   Clipped to: bookmarks/how-to-build-a-second-brain.md
   Archived in Raindrop

   2. Rust Error Handling (blog.rust-lang.org)
      Tags: #rust #programming
      → Clip to [bookmarks]: projects

   Clipped to: projects/rust-error-handling.md
   Archived in Raindrop

   3. Recipe: Sourdough (kingarthurbaking.com)
      Tags: #cooking
      → Clip to [bookmarks]: s

      Skipped.

   Done: 2 clipped, 1 skipped, 0 errors

nb inbox clear
--------------

Archive all items in inbox without clipping.

Moves items from your Raindrop inbox collection to Raindrop's Archive. Useful for clearing out items you've already read or don't need to save.

**Usage:** ``nb inbox clear [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-c, --collection TEXT``
     - Raindrop collection name
   * - ``-l, --limit INTEGER``
     - Maximum items to archive (default: 50)
   * - ``-f, --force``
     - Skip confirmation prompt

**Examples:**

.. code-block:: bash

   nb inbox clear              # Archive all items (with confirmation)
   nb inbox clear -f           # Archive without confirmation
   nb inbox clear -l 10        # Archive only 10 items
   nb inbox clear -c reading   # Clear 'reading' collection

nb inbox history
----------------

Show history of clipped inbox items.

Lists items that have been previously processed from the inbox, including which note they were clipped to and when.

**Usage:** ``nb inbox history [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-l, --limit INTEGER``
     - Maximum items to show (default: 20)
   * - ``--include-skipped``
     - Include skipped items in the list

**Examples:**

.. code-block:: bash

   nb inbox history              # Show last 20 clipped items
   nb inbox history -l 50        # Show last 50 items
   nb inbox history --include-skipped  # Include skipped items

nb inbox sync
-------------

Sync tag and note changes from Raindrop to local notes.

Checks previously-clipped items for changes in Raindrop and updates the local notes accordingly:

- **Tag changes**: Updates note frontmatter tags (preserves user-added tags)
- **Note changes**: Updates the Raindrop note section in the note content
- **Push summaries**: Pushes AI-generated summaries to Raindrop notes (if ``push_summary`` is enabled and the Raindrop note is empty)

Only syncs data that originally came from Raindrop. Tags you add locally to notes are preserved and not overwritten.

**Usage:** ``nb inbox sync [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-l, --limit INTEGER``
     - Maximum items to sync (default: 50)
   * - ``--dry-run``
     - Show what would be synced without making changes

**Examples:**

.. code-block:: bash

   nb inbox sync              # Sync up to 50 items
   nb inbox sync -l 100       # Sync up to 100 items
   nb inbox sync --dry-run    # Preview changes without applying

.. note::

   Sync must be enabled in configuration. Enable with:

   .. code-block:: bash

      nb config set inbox.raindrop.sync_tags true
      nb config set inbox.raindrop.sync_notes true

Configuration
-------------

Configure inbox settings via ``nb config set``:

.. list-table::
   :widths: 40 60
   :header-rows: 1

   * - Setting
     - Description
   * - ``inbox.source``
     - Inbox source service (currently only 'raindrop')
   * - ``inbox.default_notebook``
     - Default notebook for clipped items (default: bookmarks)
   * - ``inbox.auto_summarize``
     - Generate AI summaries when clipping (default: true)
   * - ``inbox.raindrop.collection``
     - Raindrop collection to pull from (default: nb-inbox)
   * - ``inbox.raindrop.auto_archive``
     - Move items to archive after clipping (default: true)
   * - ``inbox.raindrop.sync_tags``
     - Sync tag changes from Raindrop to notes (default: true)
   * - ``inbox.raindrop.sync_notes``
     - Sync note changes from Raindrop to notes (default: true)
   * - ``inbox.raindrop.push_summary``
     - Push AI summaries to Raindrop bookmark notes if empty (default: false)

**Example configuration in config.yaml:**

.. code-block:: yaml

   inbox:
     source: raindrop
     default_notebook: reading
     auto_summarize: true
     raindrop:
       collection: nb-inbox
       auto_archive: true
       sync_tags: true
       sync_notes: true
       push_summary: true

Duplicate Detection
-------------------

The inbox feature tracks which URLs have been clipped to prevent duplicates:

- When listing items, previously clipped URLs show a warning
- Already-clipped items are hidden by default (use ``--all`` to include them)
- Use ``d`` in interactive mode to mark an item as duplicate without clipping
- View clipping history with ``nb inbox history``
