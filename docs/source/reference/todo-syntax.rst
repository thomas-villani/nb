Todo Syntax
===========

Todos are extracted from markdown files using GitHub-style checkboxes.

Basic syntax
------------

.. code-block:: markdown

   - [ ] Pending task
   - [^] In-progress task
   - [x] Completed task

Todo status
-----------

.. list-table::
   :header-rows: 1

   * - Marker
     - Status
     - Description
   * - ``[ ]``
     - Pending
     - Task not yet started
   * - ``[^]``
     - In Progress
     - Task currently being worked on
   * - ``[x]``
     - Completed
     - Task finished

Change status with commands:

.. code-block:: bash

   nb todo start abc123    # [ ] → [^]
   nb todo pause abc123    # [^] → [ ]
   nb todo done abc123     # → [x]
   nb todo undone abc123   # [x] → [ ]

Metadata
--------

Add metadata inline after the todo text:

.. code-block:: markdown

   - [ ] Task @due(friday) @priority(1) #work #urgent

Due dates
^^^^^^^^^

Use ``@due(...)`` with flexible date formats:

.. code-block:: markdown

   - [ ] Task @due(friday)
   - [ ] Task @due(tomorrow)
   - [ ] Task @due(next week)
   - [ ] Task @due(2025-12-01)
   - [ ] Task @due(dec 15)

Priority
^^^^^^^^

Use ``@priority(1|2|3)``:

.. code-block:: markdown

   - [ ] High priority @priority(1)
   - [ ] Medium priority @priority(2)
   - [ ] Low priority @priority(3)

Tags
^^^^

Use ``#tag`` format:

.. code-block:: markdown

   - [ ] Task #work #urgent #project-alpha

**Tag format rules:**

- Must start with a letter (a-z, A-Z)
- Can contain letters, numbers, hyphens, and underscores
- Case-insensitive (stored lowercase)
- Hex color codes (e.g., ``#ff00ff``, ``#RGB``) are automatically excluded

**Valid examples:** ``#work``, ``#FY2025``, ``#project-alpha``, ``#my_tag``

**Invalid (ignored):** ``#123``, ``#ff00ff``, ``#4``

Tags are also inherited from the note's frontmatter.

Nested todos
------------

Indent with spaces to create subtasks:

.. code-block:: markdown

   - [ ] Main task
     - [ ] Subtask 1
     - [ ] Subtask 2
       - [ ] Sub-subtask
     - [x] Completed subtask

Each subtask is tracked independently with its own ID.

Multi-line details
------------------

Indented content below a todo (that isn't a checkbox) becomes details:

.. code-block:: markdown

   - [ ] Develop presentation for sales:
      - need to include intro slides
      - use the new images
      It would be best to build off the 2024 deck
   - [ ] Next task

View details with ``nb todo show``:

.. code-block:: text

   Develop presentation for sales:
   ID: abc123
   Status: Open
   Source: daily/2025-11-27.md:5

   Details:
      - need to include intro slides
      - use the new images
      It would be best to build off the 2024 deck

Todo IDs
--------

Each todo has a unique 8-character ID based on:

- File path
- Line number
- Content

The ID is stable but changes if the content changes. Use ID prefixes in commands:

.. code-block:: bash

   nb todo done abc      # Matches abc12345
   nb todo show abc123   # More specific

Grouping
--------

When listing todos, they're grouped by status and due date:

1. **OVERDUE** - Past due date
2. **IN PROGRESS** - Status ``[^]``
3. **DUE TODAY**
4. **DUE THIS WEEK**
5. **DUE NEXT WEEK**
6. **DUE LATER**
7. **NO DUE DATE**

Use focus mode (``-f``) to hide "due later" and "no date" sections.

Section targeting
-----------------

Use section headers to organize todos within a note. You can then filter or add todos to specific sections.

.. code-block:: markdown

   ## Tasks

   - [ ] First task
   - [ ] Second task

   ## Backlog

   - [ ] Future task

**Filter by section:**

.. code-block:: bash

   nb todo --note work/project::Tasks      # Only todos under "Tasks" heading
   nb todo --note project::Backlog         # Only todos under "Backlog"

**Add to section:**

.. code-block:: bash

   nb todo add "New task" --note work/project::Tasks

If the section doesn't exist, it's created as a new ``## Section`` heading.

Complete example
----------------

.. code-block:: markdown

   ---
   tags: [project, q1]
   ---

   # Sprint Planning

   ## High Priority

   - [ ] Review PR for new feature @due(friday) @priority(1) #code-review
   - [^] Implement user authentication @priority(1) #backend
     - [x] Set up database schema
     - [ ] Add password hashing
     - [ ] Create login endpoint

   ## Medium Priority

   - [ ] Schedule team meeting @due(next monday) #meetings
   - [ ] Update documentation @priority(2) #docs #maintenance
     This should cover the new API endpoints and
     include examples for each method.

   ## Done

   - [x] Send project update email #communication
