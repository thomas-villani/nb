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
   * - ``-n, --notebook TEXT``
     - Filter todos to a specific notebook
   * - ``-t, --tag TEXT``
     - Filter todos with this tag
   * - ``-o, --output [PATH]``
     - Save plan to note. Use NOTEBOOK/NOTE for specific note, NOTEBOOK for new note, or 'today'
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

   # Plan today with focus on work notebook todos
   nb plan today --notebook work

   # Interactive planning session (refine through conversation)
   nb plan week --interactive

   # Add custom instructions
   nb plan week --prompt "Focus on urgent items, skip meetings"

   # Save plan to today's daily note
   nb plan week -o today

   # Save plan to a new note in work notebook
   nb plan week -o work

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
   * - ``-n, --notebook TEXT``
     - Filter to notes in a specific notebook
   * - ``-N, --note TEXT``
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
   * - ``--agentic / --no-agentic``
     - Use agentic mode with tool-calling for complex queries

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
   nb ask "summarize project X status" -n work

   # Ask about a specific note
   nb ask "what are the action items?" -N work/meeting-notes

   # Filter by tag
   nb ask "what are our deployment procedures?" --tag infrastructure

   # Use the faster/cheaper model
   nb ask "quick summary of today" --fast

   # Disable streaming for script usage
   nb ask "list all todos mentioned" --no-stream

   # Retrieve more context for complex questions
   nb ask "comprehensive overview of the project" -k 10

   # Use agentic mode for complex queries involving todos
   nb ask "what are my overdue tasks?" --agentic

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
   nb ask "deployment checklist" -n work

   # Only search notes tagged with a project
   nb ask "current blockers" -t project-alpha

   # Ask about a specific meeting note
   nb ask "what were the action items?" -N work/2025-01-15

Model selection
^^^^^^^^^^^^^^^

- Use ``--smart`` (default) for complex questions, analysis, and summaries
- Use ``--fast`` for simple lookups and quick answers to save cost

nb summarize
------------

Generate comprehensive summaries of one or more notes using AI.

**Usage:** ``nb summarize [TARGET] [OPTIONS]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``TARGET``
     - Note path, notebook name, or date reference (e.g., "yesterday", "work", "work/meeting")

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-n, --notebook TEXT``
     - Filter to notes in a specific notebook
   * - ``-t, --tag TEXT``
     - Filter to notes with this tag
   * - ``-d, --days N``
     - Limit to notes from the last N days
   * - ``-o, --output [PATH]``
     - Save summary to note. NOTEBOOK/NOTE for specific note, NOTEBOOK for new note, or 'today'
   * - ``-fm, --front-matter``
     - Store summary in source note's YAML frontmatter
   * - ``-p, --prompt TEXT``
     - Custom instructions for the summary
   * - ``--stream / --no-stream``
     - Stream the response in real-time (default: stream)
   * - ``--smart / --fast``
     - Use smart model or fast model

**Examples:**

.. code-block:: bash

   # Summarize today's note
   nb summarize

   # Summarize yesterday's note
   nb summarize yesterday

   # Summarize all notes in a notebook
   nb summarize work

   # Summarize a specific note
   nb summarize work/meeting-notes

   # Summarize notes with a tag
   nb summarize --tag project-x

   # Week summary for a notebook
   nb summarize work --days 7

   # Save summary to today's note
   nb summarize -o today

   # Save summary to a new note in work notebook
   nb summarize -o work

   # Store in source note's frontmatter
   nb summarize --front-matter

nb tldr
-------

Generate ultra-brief 1-2 sentence summaries of notes. Like ``summarize`` but produces much shorter output.

**Usage:** ``nb tldr [TARGET] [OPTIONS]``

Options are the same as ``nb summarize``.

**Examples:**

.. code-block:: bash

   # TLDR today's note
   nb tldr

   # Week TLDR for work notebook
   nb tldr work --days 7

   # TLDR notes with a tag
   nb tldr --tag meeting

   # Save TLDR to work notebook
   nb tldr -o work

nb research
-----------

Research a topic using web search and AI analysis. Uses an agent to search the web, fetch content, and generate a comprehensive research report.

**Usage:** ``nb research QUERY [OPTIONS]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``QUERY``
     - The research topic or question

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-o, --output [PATH]``
     - Save report to note. NOTEBOOK/NOTE for specific note, NOTEBOOK for new note, or 'today'
   * - ``-s, --search TYPE``
     - Restrict to specific search types (web, news, scholar, patents). Can be repeated.
   * - ``-k, --max-sources N``
     - Maximum sources to include (default: 10)
   * - ``--strategy TYPE``
     - Research strategy: breadth, depth, or auto (default: auto)
   * - ``--token-budget N``
     - Maximum tokens to consume (default: 100000)
   * - ``--use-vectordb / --no-vectordb``
     - Use vector DB for context management (default: no)
   * - ``--stream / --no-stream``
     - Stream progress (default: stream)
   * - ``--smart / --fast``
     - Use smart model or fast model

**Requirements:**

Requires ``SERPER_API_KEY`` environment variable for web search. Get a key at https://serper.dev

**Examples:**

.. code-block:: bash

   # Research a topic
   nb research "AI trends 2025"

   # Save report to today's note
   nb research "AI trends 2025" -o today

   # Save report to a new note in work notebook
   nb research "AI trends 2025" -o work

   # Search news only
   nb research "climate change policies" --search news

   # Search academic papers
   nb research "machine learning" --search scholar

   # Use depth strategy for thorough research
   nb research "market analysis" --strategy depth --token-budget 200000
