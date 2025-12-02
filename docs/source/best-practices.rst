Best Practices
==============

Patterns and workflows for getting the most out of nb.

Organize with purpose
---------------------

Daily notebook for daily work
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use the daily notebook for day-to-day tasks, notes, and short-term todos. This keeps your inbox clean and creates a natural timeline of your work.

.. code-block:: bash

   nb                  # Open today's note
   nb ta --today "Follow up on email"

Project notebooks for long-term work
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Create dedicated notebooks for each long-running project:

.. code-block:: bash

   nb notebooks create myproject

A flat notebook structure works well for projects:

- **todo** - Main task list (consider linking from an external folder)
- **plan** - High-level roadmap and goals
- **issues** - Problems to solve, bugs to fix
- **ideas** - Future possibilities, nice-to-haves

This structure lets you quickly append items:

.. code-block:: bash

   nb add --note myproject/ideas "New feature concept"
   nb add --note myproject/issues "Bug with authentication"

Use ``todo_exclude`` strategically
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Exclude long-term project notebooks and personal notes from ``nbt`` to keep your todo list focused on actionable daily work:

.. code-block:: bash

   nb notebooks create personal --todo-exclude
   nb config exclude myproject

When you need to see a project's todos, use explicit filtering:

.. code-block:: bash

   nbt -n myproject

Master ``nbt`` workflows
------------------------

The ``nbt`` command is the heart of task management. Learn these patterns:

Filter by notebook
^^^^^^^^^^^^^^^^^^

Quickly check project-specific todos:

.. code-block:: bash

   nbt -n work          # Work notebook only
   nbt -n myproject     # Specific project

Focus mode
^^^^^^^^^^

Cut through noise with focus mode:

.. code-block:: bash

   nbt --focus          # Hide "due later" and "no date"
   nbt -n work --focus  # Combined filters

Filter by tag
^^^^^^^^^^^^^

If you use tags, filter by them:

.. code-block:: bash

   nbt -t urgent        # All urgent items
   nbt -t meeting -n work

Triage with review
^^^^^^^^^^^^^^^^^^

Use ``nbt review`` to process and organize todos:

.. code-block:: bash

   nbt review           # Interactive review mode

This helps you assign due dates, priorities, and clear out stale items.

Quick capture
^^^^^^^^^^^^^

Add todos without breaking flow:

.. code-block:: bash

   nbt add "New task @due(friday)"              # Inbox
   nbt add --note myproject/todo "Project task" # Specific note

Use ``nb open`` for editing
---------------------------

Always use ``nb open`` when editing notes or todos:

.. code-block:: bash

   nb open daily/today
   nb open myproject/todo

This ensures files are automatically reindexed after saving. Editing files directly with your editor bypasses reindexing.

Recording meetings
------------------

Create a dedicated meetings notebook:

.. code-block:: bash

   nb notebooks create meetings

Start recording before a meeting:

.. code-block:: bash

   nb record start -n meetings

This captures both microphone and computer audio, then generates a transcript.

Find things fast
----------------

History for recent work
^^^^^^^^^^^^^^^^^^^^^^^

Track down recently changed or viewed notes:

.. code-block:: bash

   nb history

Grep for exact matches
^^^^^^^^^^^^^^^^^^^^^^

Search for specific text across all notebooks:

.. code-block:: bash

   nb grep "API endpoint"
   nb grep -n work "config"  # Specific notebook

Search for concepts
^^^^^^^^^^^^^^^^^^^

Use semantic search when you remember the idea but not the words:

.. code-block:: bash

   nb search "how to deploy to production"
   nb search -s "performance optimization"

Quick reference
---------------

.. list-table::
   :widths: 40 60
   :header-rows: 1

   * - Goal
     - Command
   * - Today's todos
     - ``nbt --focus``
   * - Project todos
     - ``nbt -n project``
   * - Quick capture
     - ``nbt add "task"``
   * - Triage inbox
     - ``nbt review``
   * - Find recent notes
     - ``nb history``
   * - Search content
     - ``nb grep "text"``
   * - Record meeting
     - ``nb record start -n meetings``
