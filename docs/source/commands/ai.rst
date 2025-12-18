AI Commands
===========

AI-powered commands for intelligent note analysis, question answering, and planning.

nb plan
-------

Generate AI-assisted daily or weekly plans based on your todos, calendar, and recent notes.

**Usage:** ``nb plan [week|today] [OPTIONS]``

**Subcommands:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Subcommand
     - Description
   * - ``week``
     - Plan the upcoming week with day-by-day breakdown
   * - ``today``
     - Plan or replan today, focusing on what's achievable

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-b, --notebook TEXT``
     - Scope planning to a specific notebook
   * - ``-t, --tag TEXT``
     - Scope to todos with this tag
   * - ``-n, --note [PATH]``
     - Write plan to note (default: today's daily note if no path given)
   * - ``-p, --prompt TEXT``
     - Add custom instructions for the plan
   * - ``--no-calendar``
     - Skip Outlook calendar integration
   * - ``-i, --interactive``
     - Interactive mode to refine plan through conversation
   * - ``--stream / --no-stream``
     - Stream the response in real-time (default: stream)
   * - ``--smart / --fast``
     - Use smart model (better) or fast model (cheaper)

**How it works:**

1. Gathers incomplete todos from your notes
2. Fetches calendar events from Outlook (on Windows)
3. Reviews recent daily notes for context
4. Sends this context to the LLM with planning instructions
5. Generates a prioritized plan with warnings about overdue items

**Examples:**

.. code-block:: bash

   # Plan the upcoming week
   nb plan week

   # Plan today with focus on work notebook
   nb plan today --notebook work

   # Interactive planning session (refine through conversation)
   nb plan week --interactive

   # Add custom instructions
   nb plan week --prompt "Focus on urgent items, skip meetings"

   # Save plan to today's daily note
   nb plan week --note

   # Skip calendar integration (faster, or for non-Windows)
   nb plan today --no-calendar

**Interactive Mode:**

In interactive mode, you can refine the plan through conversation:

- Type natural requests like "move task X to Tuesday" or "add buffer time"
- Type ``save`` to save the current plan to your daily note
- Type ``done``, ``quit``, or ``exit`` to finish

**Calendar Integration:**

On Windows, the plan command can read your Outlook calendar to:

- Show scheduled meetings and events
- Calculate available time blocks
- Avoid scheduling conflicts

Install the optional dependency: ``pip install nb-cli[outlook]``

nb ask
------

Ask questions about your notes using AI-powered retrieval augmented generation (RAG).

**Usage:** ``nb ask [OPTIONS] QUESTION``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``QUESTION``
     - The question to ask about your notes

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-b, --notebook TEXT``
     - Filter to notes in a specific notebook
   * - ``-n, --note TEXT``
     - Ask about a specific note instead of searching
   * - ``-t, --tag TEXT``
     - Filter to notes with this tag
   * - ``--stream / --no-stream``
     - Stream the response in real-time (default: stream)
   * - ``--show-sources / --no-sources``
     - Show source notes used in the answer (default: show)
   * - ``--smart / --fast``
     - Use smart model (better quality) or fast model (cheaper/faster)
   * - ``-k, --max-results N``
     - Maximum number of documents to retrieve (default: 5)
   * - ``--context-window N``
     - Number of similar chunks to include per match (default: 3)

**How it works:**

1. Your question is used to search your notes using hybrid search (semantic + keyword)
2. The most relevant note chunks are retrieved as context
3. The context is sent to the LLM along with your question
4. The LLM generates an answer based only on your notes
5. Source references are provided so you can verify the information

**Examples:**

.. code-block:: bash

   # Ask a general question
   nb ask "what did we decide about the API design?"

   # Ask about notes in a specific notebook
   nb ask "summarize project X status" --notebook work

   # Ask about a specific note
   nb ask "what are the action items?" -n work/meeting-notes

   # Filter by tag
   nb ask "what are our deployment procedures?" --tag infrastructure

   # Use the faster/cheaper model
   nb ask "quick summary of today" --fast

   # Disable streaming for script usage
   nb ask "list all todos mentioned" --no-stream

   # Retrieve more context for complex questions
   nb ask "comprehensive overview of the project" -k 10

Configuration
-------------

AI features require LLM configuration. Add to your ``config.yaml``:

.. code-block:: yaml

   llm:
     provider: anthropic        # anthropic or openai
     api_key: null              # Uses ANTHROPIC_API_KEY or OPENAI_API_KEY env var
     models:
       smart: claude-sonnet-4-20250514
       fast: claude-haiku-3-5-20241022
     max_tokens: 4096
     temperature: 0.7

See :doc:`/reference/configuration` for full LLM configuration options.

**Environment variables:**

If ``api_key`` is not set in config, these environment variables are checked:

- ``ANTHROPIC_API_KEY`` - for Anthropic Claude models
- ``OPENAI_API_KEY`` - for OpenAI GPT models

Tips
----

Effective questions
^^^^^^^^^^^^^^^^^^^

- Be specific: "What did John say about the database migration?" vs "What about the database?"
- Reference timeframes: "What happened in last week's standup?"
- Ask for summaries: "Summarize the key decisions from project X meetings"
- Request lists: "List all action items from the Q4 planning notes"

Using filters
^^^^^^^^^^^^^

Filters help narrow down the search space for more relevant results:

.. code-block:: bash

   # Only search work-related notes
   nb ask "deployment checklist" -b work

   # Only search notes tagged with a project
   nb ask "current blockers" -t project-alpha

   # Ask about a specific meeting note
   nb ask "what were the action items?" -n work/2025-01-15

Model selection
^^^^^^^^^^^^^^^

- Use ``--smart`` (default) for complex questions, analysis, and summaries
- Use ``--fast`` for simple lookups and quick answers to save cost
