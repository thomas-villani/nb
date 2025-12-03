Todos Commands
==============

Commands for managing todos extracted from markdown files.

nb todo
-------

List all open todos grouped by status and due date.

**Usage:** ``nb todo [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook NAME``
     - Filter by notebook (repeatable)
   * - ``--note PATH``
     - Filter by note path or alias (repeatable)
   * - ``-t, --tag TAG``
     - Filter by tag
   * - ``-xt, --exclude-tag TAG``
     - Exclude todos with tag (repeatable)
   * - ``-p, --priority N``
     - Filter by priority (1=high, 2=medium, 3=low)
   * - ``--overdue``
     - Show only overdue todos
   * - ``-T, --today``
     - Show only todos due today
   * - ``-W, --week``
     - Show only todos due this week
   * - ``--created-today``
     - Show only todos created today
   * - ``--created-week``
     - Show only todos created this week
   * - ``-f, --focus``
     - Focus mode: hide "due later" and "no date" sections
   * - ``--hide-later``
     - Hide todos due later than next week
   * - ``--hide-no-date``
     - Hide todos with no due date
   * - ``-s, --sort-by``
     - Sort within groups: ``source``, ``tag``, ``priority``, ``created``
   * - ``-a, --all``
     - Include todos from excluded notebooks
   * - ``-c, --include-completed``
     - Include completed todos
   * - ``-i, --interactive``
     - Launch interactive TUI viewer
   * - ``-l, --limit N``
     - Limit output to N todos
   * - ``-o, --offset N``
     - Skip first N todos (for pagination)
   * - ``-v, --view NAME``
     - Apply a saved todo view
   * - ``--create-view NAME``
     - Save current filters as a view
   * - ``--list-views``
     - List all saved views
   * - ``--delete-view NAME``
     - Delete a saved view
   * - ``-x, --expand``
     - Expanded view: show more content (up to 80 chars)
   * - ``-k, --kanban``
     - Display todos in kanban board columns
   * - ``-b, --board NAME``
     - Kanban board name to use (default: 'default')

**Examples:**

.. code-block:: bash

   nb todo                    # All open todos
   nb todo -f                 # Focus mode
   nb todo -n daily -n work   # Filter by multiple notebooks
   nb todo --note myproject   # Filter by note
   nb todo -t urgent -p 1     # High priority urgent todos
   nb todo --overdue          # Overdue only
   nb todo -l 10 -o 10        # Pagination: todos 11-20
   nb todo -k                 # Kanban board view
   nb todo -k -b sprint       # Use custom board

nb todo add
-----------

Add a new todo to the inbox, today's note, or a specific note.

**Usage:** ``nb todo add [OPTIONS] [CONTENT]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``CONTENT``
     - Todo text (optional if piping from stdin)

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--today``
     - Add to today's daily note instead of inbox
   * - ``--note, -N PATH``
     - Add to specific note (supports ``note::Section`` syntax)

**Examples:**

.. code-block:: bash

   nb todo add "New task"                    # Add to inbox
   nb todo add --today "Call dentist"        # Add to today's note
   nb todo add --note work/project "Task"    # Add to specific note
   nb todo add --note proj::Tasks "Task"     # Add under section
   echo "Review PR" | nb todo add            # Pipe from stdin

The ``ta`` alias provides a shortcut:

.. code-block:: bash

   nb ta "Quick task"
   nb ta --today "Daily task"

nb todo done
------------

Mark a todo as complete.

**Usage:** ``nb todo done ID``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``ID``
     - Todo ID or ID prefix (shown in ``nb todo`` output)

**Example:**

.. code-block:: bash

   nb todo done abc123

nb todo undone
--------------

Mark a completed todo as incomplete.

**Usage:** ``nb todo undone ID``

**Example:**

.. code-block:: bash

   nb todo undone abc123

nb todo start
-------------

Mark a todo as in-progress (changes ``[ ]`` to ``[^]``).

**Usage:** ``nb todo start ID``

**Example:**

.. code-block:: bash

   nb todo start abc123

nb todo pause
-------------

Pause an in-progress todo (changes ``[^]`` to ``[ ]``).

**Usage:** ``nb todo pause ID``

**Example:**

.. code-block:: bash

   nb todo pause abc123

nb todo show
------------

Show todo details including multi-line content.

**Usage:** ``nb todo show ID``

**Example:**

.. code-block:: bash

   nb todo show abc123

Output:

.. code-block:: text

   Review documentation for API changes
   ID: abc12345
   Status: Open
   Source: work/api-update.md:15

   Details:
      - Check authentication section
      - Verify rate limiting docs

nb todo edit
------------

Open the source file at the todo's line.

**Usage:** ``nb todo edit ID``

**Example:**

.. code-block:: bash

   nb todo edit abc123

nb todo due
-----------

Set or clear the due date for a todo.

**Usage:** ``nb todo due ID... DATE_EXPR``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``ID``
     - Todo ID or ID prefix (can specify multiple)
   * - ``DATE_EXPR``
     - Date expression or "none"/"clear" to remove due date

**Date expressions:**

- Weekday names: ``friday``, ``monday`` (means the **next** occurrence)
- Relative: ``tomorrow``, ``next week``, ``next monday``
- Natural language: ``dec 25``, ``december 25 2025``
- ISO format: ``2025-12-15``
- Clear keywords: ``none``, ``clear``, ``remove``

**Examples:**

.. code-block:: bash

   nb todo due abc123 friday       # Set due to next Friday
   nb todo due abc123 tomorrow     # Set due to tomorrow
   nb todo due abc123 "dec 25"     # Set due to specific date
   nb todo due abc123 none         # Remove due date
   nb todo due abc def friday      # Set multiple todos at once

nb todo all-done
----------------

Mark all todos in a note as completed.

**Usage:** ``nb todo all-done NOTE_REF [OPTIONS]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``NOTE_REF``
     - Note name, path (notebook/note), or alias

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook``
     - Notebook to search in
   * - ``-f, --force``
     - Skip confirmation prompt

**Examples:**

.. code-block:: bash

   nb todo all-done friday             # Friday's daily note
   nb todo all-done myproject -n work  # work/myproject.md
   nb todo all-done work/myproject     # Same as above
   nb todo all-done myalias            # By note alias
   nb todo all-done friday -f          # Skip confirmation

nb todo completed
-----------------

Show recently completed todos grouped by completion date.

**Usage:** ``nb todo completed [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-T, --today``
     - Show todos completed today
   * - ``-Y, --yesterday``
     - Show todos completed yesterday
   * - ``-W, --week``
     - Show todos completed this week
   * - ``-d, --days N``
     - Show todos completed in last N days
   * - ``-n, --notebook NAME``
     - Filter by notebook (repeatable)
   * - ``-t, --tag TAG``
     - Filter by tag
   * - ``-l, --limit N``
     - Maximum number of todos (default: 50)

**Examples:**

.. code-block:: bash

   nb todo completed              # Completed in last 7 days (default)
   nb todo completed --today      # Completed today
   nb todo completed --yesterday  # Completed yesterday
   nb todo completed --week       # Completed this week
   nb todo completed -d 30        # Completed in last 30 days
   nb todo completed -n work      # From work notebook only
   nb todo completed -t project   # Todos tagged #project

Interactive mode
----------------

Launch an interactive TUI for managing todos:

.. code-block:: bash

   nb todo -i

**Keyboard shortcuts:**

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Key
     - Action
   * - ``j/k``
     - Navigate up/down
   * - ``Space``
     - Toggle completion
   * - ``s``
     - Toggle in-progress (start/pause)
   * - ``e``
     - Edit source file
   * - ``c``
     - Toggle showing completed
   * - ``g/G``
     - Jump to top/bottom
   * - ``r``
     - Refresh
   * - ``q``
     - Quit

Kanban view
-----------

Display todos in a kanban board layout with customizable columns:

.. code-block:: bash

   nb todo --kanban           # Display default kanban board
   nb todo -k                 # Short form
   nb todo -k -b sprint       # Use a custom board

The default board has four columns: Backlog, In Progress, Due Today, and Done.

**Custom Boards**

Configure custom boards in ``config.yaml``:

.. code-block:: yaml

   kanban_boards:
     - name: sprint
       columns:
         - name: "To Do"
           filters: { status: pending, no_due_date: true }
           color: cyan
         - name: "In Progress"
           filters: { status: in_progress }
           color: green
         - name: "Done"
           filters: { status: completed }
           color: dim

**Available column filters:**

- ``status``: "pending", "in_progress", or "completed"
- ``due_today``: true - todos due today
- ``due_this_week``: true - todos due within 7 days
- ``overdue``: true - past due, not completed
- ``no_due_date``: true - todos without a due date
- ``priority``: 1, 2, or 3
- ``tags``: list of tags to filter by

The web UI also includes a Kanban view with drag-and-drop support to move todos between columns.

Saved views
-----------

Save filter configurations for quick access:

.. code-block:: bash

   # Create a view
   nb todo -n work -t urgent --create-view work-urgent

   # Use a view
   nb todo -v work-urgent

   # List views
   nb todo --list-views

   # Delete a view
   nb todo --delete-view work-urgent

Todo exclusion
--------------

Todos can be hidden from ``nb todo`` at multiple levels:

Notebook level
^^^^^^^^^^^^^^

Set in config when creating or via ``nb config``:

.. code-block:: bash

   nb notebooks create personal --todo-exclude
   nb config exclude personal

Note level
^^^^^^^^^^

Set in note frontmatter:

.. code-block:: yaml

   ---
   todo_exclude: true
   ---

Or via command:

.. code-block:: bash

   nb config exclude projects/old-idea

Linked note level
^^^^^^^^^^^^^^^^^

When linking external files:

.. code-block:: bash

   nb link add ~/archive --todo-exclude

Use ``-a`` or ``-n <notebook>`` to view excluded todos.

Command aliases
---------------

.. list-table::
   :header-rows: 1

   * - Alias
     - Command
   * - ``td``
     - ``todo``
   * - ``ta``
     - ``todo add``
   * - ``nbt``
     - Standalone equivalent to ``nb todo``
