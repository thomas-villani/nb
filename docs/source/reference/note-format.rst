Note Format
===========

Notes are markdown files with optional YAML frontmatter.

Directory structure
-------------------

Notes are organized in the notes root directory (default: ``~/notes``):

.. code-block:: text

   ~/notes/
   ├── daily/                    # Date-based notebook
   │   └── 2025/
   │       ├── Nov18-Nov24/
   │       │   └── 2025-11-20.md
   │       └── Nov25-Dec01/      # Week folders (Mon-Sun)
   │           ├── 2025-11-26.md
   │           └── 2025-11-27.md
   ├── projects/                 # Flat notebook
   │   └── myproject.md
   ├── work/
   ├── todo.md                   # Todo inbox
   └── .nb/
       ├── config.yaml
       ├── index.db              # SQLite database
       ├── vectors/              # Search embeddings
       ├── templates/            # Note templates
       └── attachments/          # Copied attachments

Date-based notebooks organize notes by work week (Monday-Sunday).

Frontmatter
-----------

Frontmatter is optional YAML metadata at the top of the file:

.. code-block:: yaml

   ---
   date: 2025-11-27
   title: Meeting Notes
   tags: [meeting, project, quarterly]
   todo_exclude: true
   ---

   # Your note content here

Available fields:

.. list-table::
   :header-rows: 1

   * - Field
     - Description
   * - ``date``
     - Note date (YYYY-MM-DD format)
   * - ``title``
     - Note title (used in search results)
   * - ``tags``
     - List of tags for filtering
   * - ``todo_exclude``
     - Hide todos from ``nb todo``
   * - ``links``
     - List of related notes/URLs (see below)

Links in frontmatter
^^^^^^^^^^^^^^^^^^^^

The ``links`` field supports several formats:

.. code-block:: yaml

   ---
   links:
     # String formats
     - "note://work/project-plan"    # Internal note link
     - "https://example.com"          # External URL

     # Object format for URLs
     - title: "Company Wiki"
       url: "https://wiki.example.com"

     # Object format for notes
     - title: "Project Plan"
       note: "2026-plan"
       notebook: "work"              # Optional notebook context
   ---

Tag inheritance
^^^^^^^^^^^^^^^

Tags in frontmatter are inherited by all todos in the note. If a note has:

.. code-block:: yaml

   ---
   tags: [project, urgent]
   ---

Then all todos in that note will have ``#project`` and ``#urgent`` tags in addition to any inline tags.

Templates
---------

Templates are stored in ``.nb/templates/`` as markdown files.

Template variables
^^^^^^^^^^^^^^^^^^

Use these variables in templates - they're replaced when creating notes:

.. list-table::
   :header-rows: 1

   * - Variable
     - Description
   * - ``{{ date }}``
     - ISO date (2025-11-29)
   * - ``{{ datetime }}``
     - ISO datetime
   * - ``{{ notebook }}``
     - Notebook name
   * - ``{{ title }}``
     - Note title

Example template
^^^^^^^^^^^^^^^^

Create ``.nb/templates/meeting.md``:

.. code-block:: markdown

   ---
   date: {{ date }}
   ---

   # {{ title }}

   ## Attendees

   -

   ## Agenda

   -

   ## Notes

   ## Action Items

   - [ ]

Use it when creating notes:

.. code-block:: bash

   nb new standup -n work -T meeting

Default templates
^^^^^^^^^^^^^^^^^

Configure a default template for a notebook in config:

.. code-block:: yaml

   notebooks:
     - name: work
       date_based: true
       template: meeting

Attachments
-----------

Attach files or URLs using the ``@attach:`` syntax:

.. code-block:: markdown

   @attach: ~/Documents/spec.pdf
   @attach: ./relative/path/to/file.png
   @attach: https://example.com/resource
   @attach: [Custom Title](~/path/to/file.pdf)

Note linking
------------

Create connections between notes using wiki-style or markdown links.

**Wiki-style links:**

.. code-block:: markdown

   See [[projects/myproject]] for details.
   Also check [[myproject|the project docs]] for examples.

**Markdown links:**

.. code-block:: markdown

   For more info, read [the API guide](docs/api.md).
   Visit [our wiki](https://wiki.example.com).
   See [related note](./relative.md).

.. list-table::
   :header-rows: 1

   * - Syntax
     - Description
   * - ``[[path]]``
     - Wiki-style link to note
   * - ``[[path|display]]``
     - Wiki-style link with custom text
   * - ``[text](path.md)``
     - Markdown link to internal note
   * - ``[text](https://...)``
     - Markdown link to external URL
   * - ``[text](./relative.md)``
     - Relative path (resolved from note's directory)

Use ``nb links`` to see outgoing links and ``nb backlinks`` to see incoming links.

Attachments
-----------

Attach files or URLs using the ``@attach:`` syntax:

.. code-block:: markdown

   @attach: ~/Documents/spec.pdf
   @attach: ./relative/path/to/file.png
   @attach: https://example.com/resource
   @attach: [Custom Title](~/path/to/file.pdf)

Attachments can also be added via command:

.. code-block:: bash

   nb attach file ./doc.pdf
   nb attach url https://example.com

Complete example
----------------

A full note with frontmatter, content, todos, and attachments:

.. code-block:: markdown

   ---
   date: 2025-11-27
   title: Project Kickoff Meeting
   tags: [meeting, project, quarterly]
   ---

   # Project Kickoff Meeting

   Met with the team to discuss Q1 priorities.

   ## Attendees

   - Alice, Bob, Charlie

   ## Discussion

   Reviewed the roadmap and assigned initial tasks.

   ## Action Items

   - [ ] Write project specification @due(friday) @priority(1) #docs
   - [ ] Set up CI/CD pipeline @due(next week) @priority(2) #devops
   - [ ] Review competitor analysis @due(dec 15) #research
   - [x] Send meeting notes to stakeholders #communication

   ## Attachments

   @attach: ~/Documents/roadmap-2025.pdf
   @attach: https://wiki.company.com/project-alpha
