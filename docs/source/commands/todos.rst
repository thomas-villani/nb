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
   * - ``-T, --exclude-tag TAG``
     - Exclude todos with tag (repeatable)
   * - ``-p, --priority N``
     - Filter by priority (1=high, 2=medium, 3=low)
   * - ``--overdue``
     - Show only overdue todos
   * - ``--due-today``
     - Show only todos due today
   * - ``--due-week``
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

**Examples:**

.. code-block:: bash

   nb todo                    # All open todos
   nb todo -f                 # Focus mode
   nb todo -n daily -n work   # Filter by multiple notebooks
   nb todo --note myproject   # Filter by note
   nb todo -t urgent -p 1     # High priority urgent todos
   nb todo --overdue          # Overdue only
   nb todo -l 10 -o 10        # Pagination: todos 11-20

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
