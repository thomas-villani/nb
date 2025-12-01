Quick Start
===========

This guide will get you up and running with nb in a few minutes.

Your first note
---------------

Run ``nb`` without arguments to open today's daily note:

.. code-block:: bash

   nb

This creates and opens a markdown file organized by week:

.. code-block:: text

   ~/notes/daily/2025/Nov25-Dec01/2025-11-27.md

To view the note in your terminal instead of opening an editor:

.. code-block:: bash

   nb -s

Adding todos
------------

Add a todo to your inbox:

.. code-block:: bash

   nb todo add "Review pull request @due(friday) #work"

Add a todo directly to today's note:

.. code-block:: bash

   nb todo add --today "Call dentist @due(tomorrow)"

List your todos:

.. code-block:: bash

   nb todo

Todos are grouped by status and due date: overdue, in progress, due today, due this week, etc.

.. image:: /_static/examples/todo-list.svg
   :alt: nb todo output
   :width: 100%

Working with todos
------------------

Mark a todo complete (use the ID prefix shown in ``nb todo``):

.. code-block:: bash

   nb todo done abc123

Start working on a todo (changes ``[ ]`` to ``[^]``):

.. code-block:: bash

   nb todo start abc123

Edit the source file at the todo's line:

.. code-block:: bash

   nb todo edit abc123

Searching notes
---------------

Search across all your notes:

.. code-block:: bash

   nb search "project ideas"

Use semantic search to find conceptually related content:

.. code-block:: bash

   nb search -s "how to improve performance"

Multiple notebooks
------------------

Create notebooks to organize different types of notes:

.. code-block:: bash

   nb notebooks create work --date-based
   nb notebooks create ideas

Open today's note in a specific notebook:

.. code-block:: bash

   nb -n work

List your notebooks:

.. code-block:: bash

   nb notebooks

.. image:: /_static/examples/notebooks.svg
   :alt: nb notebooks output
   :width: 80%

Next steps
----------

- See :doc:`commands/notes` for all note management commands
- See :doc:`commands/todos` for advanced todo features
- See :doc:`reference/todo-syntax` for todo metadata syntax
- See :doc:`reference/configuration` for customization options
