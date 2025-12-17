Git Integration
===============

Version control your notes and sync with GitHub or other git remotes.

The git integration provides:

- Initialize a git repository in your notes directory
- Auto-commit after note changes (create, edit, delete, move)
- Manual commit, push, pull, and sync commands
- Conflict detection with clear resolution instructions

Setup
-----

1. **Initialize git repository:**

   .. code-block:: bash

      nb git init

   This creates a ``.git`` directory and a ``.gitignore`` that excludes the ``.nb/`` cache directory.

2. **Add a remote (e.g., GitHub):**

   .. code-block:: bash

      nb git remote --add git@github.com:username/notes.git

   Or initialize with remote in one step:

   .. code-block:: bash

      nb git init --remote git@github.com:username/notes.git

3. **Enable auto-commits:**

   .. code-block:: bash

      nb config set git.enabled true

4. **Push existing notes:**

   .. code-block:: bash

      nb git push

nb git init
-----------

Initialize a git repository in the notes root directory.

Creates a ``.git`` directory and a ``.gitignore`` file that excludes:

- ``.nb/`` directory (database, vectors, attachments)
- Common temporary files (``.DS_Store``, ``*.swp``, etc.)

**Usage:** ``nb git init [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-r, --remote TEXT``
     - Remote repository URL to add as origin

**Examples:**

.. code-block:: bash

   nb git init
   nb git init --remote git@github.com:user/notes.git

nb git status
-------------

Show the git status of the notes repository.

Displays branch name, ahead/behind counts, and lists of staged, modified, and untracked files.

**Usage:** ``nb git status [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-v, --verbose``
     - Show individual file names in each category

**Examples:**

.. code-block:: bash

   nb git status
   nb git status -v

**Example Output:**

.. code-block:: text

   Branch: main
   Ahead by 2 commit(s)

   Staged changes: 1 file(s)
   Modified: 3 file(s)
   Untracked: 2 file(s)

nb git commit
-------------

Manually commit all changes with a message.

Stages all changes (modified, deleted, new files) and creates a commit.

**Usage:** ``nb git commit [MESSAGE] [OPTIONS]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``MESSAGE``
     - Commit message (optional, defaults to "Manual commit via nb")

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-a, --all``
     - Commit all changes (same behavior, for compatibility)

**Examples:**

.. code-block:: bash

   nb git commit "Weekly review complete"
   nb git commit --all
   nb git commit

nb git push
-----------

Push commits to the remote repository.

**Usage:** ``nb git push [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-r, --remote TEXT``
     - Remote name (default: origin)
   * - ``-f, --force``
     - Force push (use with caution, prompts for confirmation)

**Examples:**

.. code-block:: bash

   nb git push
   nb git push --remote upstream

nb git pull
-----------

Pull changes from the remote repository.

If merge conflicts are detected, the merge is aborted and instructions are provided for manual resolution.

**Usage:** ``nb git pull [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-r, --remote TEXT``
     - Remote name (default: origin)

**Examples:**

.. code-block:: bash

   nb git pull
   nb git pull --remote upstream

**Conflict Handling:**

When conflicts are detected, you'll see:

.. code-block:: text

   Merge conflicts detected. Please resolve manually:
     cd ~/notes
     git pull origin main
     # Resolve conflicts, then: git add . && git commit

nb git sync
-----------

Pull then push in one command.

Convenience command equivalent to ``nb git pull && nb git push``.

**Usage:** ``nb git sync``

**Examples:**

.. code-block:: bash

   nb git sync

nb git log
----------

Show commit history.

**Usage:** ``nb git log [OPTIONS]``

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --limit INTEGER``
     - Number of commits to show (default: 10)
   * - ``--oneline``
     - Compact one-line format

**Examples:**

.. code-block:: bash

   nb git log
   nb git log -n 20
   nb git log --oneline

**Example Output:**

.. code-block:: text

   Commit: a1b2c3d4e5f6...
   Author: Your Name <you@example.com>
   Date:   2025-01-15 14:30:00

       Update daily/2025-01-15.md

nb git remote
-------------

Manage remote repository configuration.

**Usage:** ``nb git remote [URL] [OPTIONS]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``URL``
     - Remote repository URL (required with ``--add``)

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-a, --add``
     - Add remote origin
   * - ``-r, --remove``
     - Remove remote origin

**Examples:**

.. code-block:: bash

   nb git remote                              # Show current remote
   nb git remote --add git@github.com:user/notes.git
   nb git remote --remove

Auto-Commit
-----------

When git integration is enabled (``git.enabled: true``), nb automatically commits after:

- **Creating notes:** ``nb new``, ``nb today`` (first edit)
- **Editing notes:** After closing editor via ``nb open``, ``nb edit``
- **Deleting notes:** ``nb delete``
- **Moving notes:** ``nb mv``

Auto-commits use a configurable message template. The default is ``Update {path}``.

**Template Variables:**

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Variable
     - Description
   * - ``{path}``
     - Relative path to the note (e.g., ``daily/2025-01-15.md``)
   * - ``{notebook}``
     - Notebook name (e.g., ``daily``)
   * - ``{title}``
     - Note filename without extension (e.g., ``2025-01-15``)
   * - ``{date}``
     - Current date in YYYY-MM-DD format

Configuration
-------------

Configure git settings via ``nb config set``:

.. list-table::
   :widths: 40 60
   :header-rows: 1

   * - Setting
     - Description
   * - ``git.enabled``
     - Enable git integration (default: false)
   * - ``git.auto_commit``
     - Auto-commit after note changes (default: true)
   * - ``git.commit_message_template``
     - Commit message template (default: "Update {path}")

**Examples:**

.. code-block:: bash

   nb config set git.enabled true
   nb config set git.auto_commit false
   nb config set git.commit_message_template "nb: {notebook}/{title}"

**Configuration in config.yaml:**

.. code-block:: yaml

   git:
     enabled: true
     auto_commit: true
     commit_message_template: "Update {path}"

Workflow Example
----------------

**Initial Setup:**

.. code-block:: bash

   # Initialize git
   nb git init

   # Add GitHub remote
   nb git remote --add git@github.com:user/my-notes.git

   # Enable auto-commits
   nb config set git.enabled true

   # Commit and push existing notes
   nb git commit "Initial commit"
   nb git push

**Daily Workflow:**

.. code-block:: bash

   # Work on notes (auto-commits happen automatically)
   nb today                    # Opens daily note, auto-commits on save
   nb new ideas/brainstorm     # Creates note, auto-commits
   nb delete old-draft         # Deletes note, auto-commits

   # Sync with remote at end of day
   nb git sync                 # Pull + push

**Checking Status:**

.. code-block:: bash

   nb git status               # See uncommitted changes
   nb git log --oneline        # Review recent commits

Syncing Across Devices
----------------------

With git integration, you can sync your notes across multiple devices:

1. **On first device:** Initialize and push to GitHub

   .. code-block:: bash

      nb git init --remote git@github.com:user/notes.git
      nb config set git.enabled true
      nb git push

2. **On second device:** Clone the repository

   .. code-block:: bash

      git clone git@github.com:user/notes.git ~/notes
      cd ~/notes
      nb config set git.enabled true

3. **Regular sync:** Pull before working, auto-commits as you work, push when done

   .. code-block:: bash

      nb git pull               # Get latest changes
      # ... work on notes ...
      nb git push               # Push your changes

   Or use ``nb git sync`` for pull + push in one command.

.. note::

   The ``.nb/`` directory (containing the database and vector index) is excluded from git. Each device maintains its own local index, which is rebuilt as needed with ``nb index``.
