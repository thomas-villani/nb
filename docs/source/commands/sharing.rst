Multiplayer Notebooks
=====================

Share *some* of your notebooks with teammates over git — without sharing your whole
notes tree — and track who owns which todos. This is built for collaborative project
and task management.

What you get:

- **Shared notebooks** that sync over git, while the rest of your notes stay private.
- **Todo ownership** with ``@owner(handle)`` and filters like ``nb todo --mine``.
- **Existing-repo integration** — hang shared notes off a code repo you already have.

How It Works
------------

A *shared notebook* is an external notebook whose content lives inside its own
standalone git repository with a remote. Your ``notes_root`` stays private (it does
not even need to be a git repo), and only the shared notebook's directory is pushed
to a shared remote.

Your configuration (``.nb/config.yaml``) is **per-machine and never shared** — it is
excluded from git. So each teammate registers the same shared notebook independently,
pointing at their own local clone. The markdown files are the source of truth; the
local index is rebuilt on each sync.

.. note::

   Because config is local, two teammates can map the same shared repo to different
   notebook names if they like. What syncs is the markdown content of the shared
   repository, not anyone's config.

Quick Start
-----------

**Set your identity** (once per machine). This attributes todos and powers
``nb todo --mine``:

.. code-block:: bash

   nb team set --name "Thomas Villani" --handle thomas
   nb team whoami

**Create and publish a shared notebook** (the person starting the project):

.. code-block:: bash

   # You already have an internal notebook called 'projectx' with some notes
   nb share init projectx --remote git@github.com:team/projectx.git

**Join an existing shared notebook** (a teammate):

.. code-block:: bash

   nb share add git@github.com:team/projectx.git projectx

**Assign and track work:**

.. code-block:: bash

   nb todo add "Ship the API @owner(federico) @due(friday) #backend" -n projectx
   nb todo --owner federico        # what Federico owns
   nb todo --mine                  # what you own

**Sync (pull teammates' changes, push yours):**

.. code-block:: bash

   nb share sync

Identity (nb team)
------------------

Your identity is stored per-machine in ``config.team`` and is used to attribute todos
and resolve ``nb todo --mine``. Any blank field falls back to your git
``user.name`` / ``user.email``; if you do not set a handle, one is derived from your
name or email.

nb team set
~~~~~~~~~~~

Set one or more identity fields.

**Usage:** ``nb team set [OPTIONS]``

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``--name TEXT``
     - Your display name (e.g. "Thomas Villani")
   * - ``--handle TEXT``
     - Short handle used in ``@owner(handle)`` (e.g. ``thomas``)
   * - ``--email TEXT``
     - Your email, for attribution

**Examples:**

.. code-block:: bash

   nb team set --name "Thomas Villani" --handle thomas --email tom@example.com
   nb team set --handle thomas

nb team whoami
~~~~~~~~~~~~~~

Show your resolved identity and where each field came from (config or git).

**Usage:** ``nb team whoami``

**Example Output:**

.. code-block:: text

   Name:   Thomas Villani
   Handle: thomas
   Email:  tom@example.com
   Source: config

Todo Ownership
--------------

Assign a todo to someone by adding ``@owner(handle)`` (or the alias ``@for(handle)``)
to the todo text. It is parsed exactly like ``@due`` and ``@priority`` and is stripped
from the displayed task description.

.. code-block:: text

   - [ ] Ship the API @owner(federico) @due(friday) #backend
   - [ ] Write the migration @for(thomas)

Filter by owner:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Command
     - Description
   * - ``nb todo --owner <handle>``
     - Show todos owned by a specific handle (``-O`` for short)
   * - ``nb todo --mine``
     - Show todos owned by you (your configured handle)

**Examples:**

.. code-block:: bash

   nb todo --owner federico
   nb todo -O federico -n projectx     # combine with any other filter
   nb todo --mine

.. note::

   Ownership matches the ``@owner()`` token in the todo's text, so it is consistent
   for everyone on the team regardless of where each person's clone lives on disk.

Shared Notebooks (nb share)
---------------------------

nb share init
~~~~~~~~~~~~~

Promote an existing **internal** notebook into a shared, git-backed notebook. Moves the
notebook out to its own git repository, initializes it (with a ``.gitignore``), and
optionally adds a remote and pushes.

**Usage:** ``nb share init NAME [OPTIONS]``

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument / Option
     - Description
   * - ``NAME``
     - Name of an existing internal notebook to promote
   * - ``-r, --remote TEXT``
     - Remote URL to add as ``origin`` and push to

**Examples:**

.. code-block:: bash

   nb share init projectx
   nb share init projectx --remote git@github.com:team/projectx.git

By default the repository is created under ``<notes_root>/.nb/shared/<name>``.

nb share add
~~~~~~~~~~~~

Register a shared notebook from a git URL or an existing local repository.

- Given a **git URL**, it is cloned into ``<notes_root>/.nb/shared/<name>``.
- Given a path to an **existing local working tree**, it is registered in place — useful
  for hanging nb notes off a code repo you already have checked out. Sync then happens
  through that repository's normal git workflow.

**Usage:** ``nb share add SOURCE NAME [OPTIONS]``

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument / Option
     - Description
   * - ``SOURCE``
     - A git remote URL, or a path to an existing local git repo
   * - ``NAME``
     - Notebook name to register
   * - ``--subdir TEXT``
     - Content directory within the repo (e.g. ``docs`` or ``.nbnotes``)
   * - ``-d, --date-based TEXT``
     - Date mode: ``false``, ``daily``, or ``weekly``

**Examples:**

.. code-block:: bash

   # Clone a teammate's shared notebook
   nb share add git@github.com:team/projectx.git projectx

   # Hang notes off an existing code repo, in a dedicated subfolder
   nb share add ~/repos/somecode projnotes --subdir .nbnotes

   # Or track markdown that already lives in the repo (e.g. docs/)
   nb share add ~/repos/somecode projnotes --subdir docs

.. note::

   When ``--subdir`` is used, the notebook's content is that subfolder, but all git
   operations target the **repository root** (the enclosing ``.git``). This is what lets
   a shared notebook live inside a larger project repository.

nb share list
~~~~~~~~~~~~~

List your shared notebooks with their sync status (branch, ahead/behind, dirty).

**Usage:** ``nb share list``

**Example Output:**

.. code-block:: text

   projectx
     path: ~/notes/.nb/shared/projectx
     branch: main  ↑1 dirty

nb share status
~~~~~~~~~~~~~~~

Show git status for one or all shared notebooks.

**Usage:** ``nb share status [NAME]``

**Examples:**

.. code-block:: bash

   nb share status            # all shared notebooks
   nb share status projectx   # just one

nb share sync
~~~~~~~~~~~~~

Sync one or all shared notebooks. For each notebook this:

1. Commits any uncommitted local edits in that notebook's repository.
2. Pulls from and pushes to the remote.
3. Re-indexes the notebook so search and todos reflect the latest content.

Conflicts and errors are **isolated per notebook** — a problem with one shared notebook
does not stop the others from syncing.

**Usage:** ``nb share sync [NAME]``

**Examples:**

.. code-block:: bash

   nb share sync              # sync all shared notebooks
   nb share sync projectx     # sync only 'projectx'

**Example Output:**

.. code-block:: text

   projectx: pulled, pushed (3 files indexed)

**Conflict Handling:**

If a notebook has a merge conflict, the merge is aborted and you are given manual
resolution steps, while other notebooks still sync:

.. code-block:: text

   projectx: merge conflict
   Merge conflicts detected. Please resolve manually:
     cd ~/notes/.nb/shared/projectx
     git pull origin main
     # Resolve conflicts, then: git add . && git commit

End-to-End Example
------------------

**Thomas starts a shared project and invites Federico:**

.. code-block:: bash

   # Thomas (machine A)
   nb team set --handle thomas
   nb new projectx/plan                          # jot down some notes
   nb share init projectx --remote git@github.com:team/projectx.git

**Federico joins from his own machine:**

.. code-block:: bash

   # Federico (machine B)
   nb team set --handle federico
   nb share add git@github.com:team/projectx.git projectx
   nb todo --mine -n projectx                    # see what's assigned to him

**They divide the work and sync:**

.. code-block:: bash

   # Federico assigns a task to Thomas and syncs
   nb todo add "Review the API design @owner(thomas)" -n projectx
   nb share sync

   # Thomas pulls it in
   nb share sync
   nb todo --mine                                # 'Review the API design' now appears

Hanging Notes Off an Existing Repo
----------------------------------

If you and your team already collaborate on a code repository, you can track project
todos there without restructuring anything:

.. code-block:: bash

   # Keep nb notes in a dedicated folder inside the repo
   nb share add ~/repos/teamproject projtodos --subdir .nbnotes

   # Add tasks; they live in ~/repos/teamproject/.nbnotes/*.md
   nb todo add "Wire up auth @owner(federico)" -n projtodos

Because the notebook points inside an existing repo, you can sync with ``nb share sync``
**or** simply commit and push the repo the way you normally do — the markdown files are
just part of the project.

Tips & Notes
------------

- **Keep API/secret notes out of shared notebooks.** Anything in a shared notebook is
  pushed to its remote.
- **The local index is disposable.** ``.nb/`` (database and vectors) is never shared;
  ``nb share sync`` rebuilds the index for the synced notebook automatically. You can
  always run ``nb index --force`` to rebuild everything.
- **Your identity is local.** ``nb team`` settings are per-machine and never committed.
- **Conflicts are rare for todos** since each todo is its own line, but if two people
  edit the same line, resolve it with normal git in the shared notebook's repository.
