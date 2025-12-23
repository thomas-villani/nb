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

nb review
---------

Generate AI-assisted daily or weekly reviews reflecting on completed work, items carrying over, wins, and areas for improvement.

**Usage:** ``nb review [day|week] [OPTIONS]``

**Subcommands:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Subcommand
     - Description
   * - ``day``
     - Generate an end-of-day review
   * - ``week``
     - Generate an end-of-week review with improvement suggestions

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
     - Save review to note. Use NOTEBOOK/NOTE for specific note, NOTEBOOK for new note, or 'today'
   * - ``-p, --prompt TEXT``
     - Add custom instructions for the review
   * - ``--stream / --no-stream``
     - Stream the response in real-time (default: stream)
   * - ``--smart / --fast``
     - Use smart model (better) or fast model (cheaper)

**How it works:**

1. Gathers completed todos from the period (today or this week)
2. Collects pending todos that are carrying over
3. Identifies overdue items needing attention
4. Sends this context to the LLM with review prompts
5. Generates a structured review with sections

**Review Sections:**

- **Completed** - What got done, grouped by project/notebook
- **Carrying Over** - Pending items moving forward with brief context
- **Wins** - Notable achievements, milestones, or progress
- **Improvements** (weekly only) - Process improvement suggestions based on patterns

**Examples:**

.. code-block:: bash

   # End of day review
   nb review day

   # End of day review for work notebook
   nb review day --notebook work

   # Weekly review
   nb review week

   # Save review to today's daily note
   nb review week -o today

   # Save review to a new note in work notebook
   nb review week -o work

   # Save review to a specific note
   nb review week -o work/weekly-reviews

   # Add custom focus
   nb review week --prompt "Focus on wins and blockers"

   # Use faster/cheaper model
   nb review day --fast

nb standup
----------

Generate an AI-powered morning standup briefing based on yesterday's completed work, today's calendar, and items needing attention.

**Usage:** ``nb standup [OPTIONS]``

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
     - Save standup to note. Use NOTEBOOK/NOTE for specific note, NOTEBOOK for new note, or 'today'
   * - ``-p, --prompt TEXT``
     - Add custom instructions for the standup
   * - ``--no-calendar``
     - Skip Outlook calendar integration
   * - ``--stream / --no-stream``
     - Stream the response in real-time (default: stream)
   * - ``--smart / --fast``
     - Use smart model (better) or fast model (cheaper)

**How it works:**

1. Gathers completed todos from yesterday
2. Fetches today's calendar events from Outlook (on Windows)
3. Collects overdue and in-progress todos
4. Identifies todos due today
5. Generates a focused morning briefing

**Standup Sections:**

- **Yesterday** - Brief 1-2 sentence summary of completed work
- **Today's Schedule** - Calendar events and meetings to be aware of
- **Focus Areas** - Top 2-3 priorities based on due dates and importance
- **Needs Attention** - Overdue items or stale tasks requiring action

**Examples:**

.. code-block:: bash

   # Morning standup briefing
   nb standup

   # Focus on work notebook todos
   nb standup --notebook work

   # Save to today's daily note
   nb standup -o today

   # Save to a new note in work notebook
   nb standup -o work

   # Skip calendar integration (faster, or for non-Windows)
   nb standup --no-calendar

   # Use faster/cheaper model
   nb standup --fast

   # Add custom instructions
   nb standup --prompt "Prioritize client-facing tasks"

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

nb assistant
------------

An interactive AI agent that can analyze your todos and notes, and take action on your behalf.
All write operations require confirmation before executing.

**Usage:** ``nb assistant [QUERY] [OPTIONS]``

**Arguments:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Argument
     - Description
   * - ``QUERY``
     - Optional initial query to start the conversation

**Options:**

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Description
   * - ``-f, --file PATH``
     - Include file(s) as context (can be repeated)
   * - ``--paste``
     - Include clipboard content as context
   * - ``-N, --note TEXT``
     - Include specific note(s) as context (notebook/note format, can be repeated)
   * - ``-n, --notebook TEXT``
     - Focus context on a specific notebook
   * - ``--no-calendar``
     - Skip Outlook calendar integration
   * - ``--smart / --fast``
     - Use smart model (better) or fast model (cheaper)
   * - ``--dry-run``
     - Show proposed changes without executing them
   * - ``--token-budget N``
     - Maximum tokens to consume per session (default: 100000)
   * - ``--max-tools N``
     - Maximum tool calls per turn (default: 10)

**How it works:**

1. Gathers context automatically (overdue todos, in-progress tasks, calendar, recent notes)
2. Optionally includes additional context from files, clipboard, or specific notes
3. You interact with the agent conversationally
4. Read operations execute immediately (search, query todos, etc.)
5. Write operations are queued for your review and confirmation
6. You can approve all changes, select specific ones, or discard them

**Available Tools:**

The assistant has access to these tools:

*Read Tools (execute immediately):*

- ``search_notes`` - Semantic search over your notes
- ``read_note`` - Read full content of a specific note
- ``query_todos`` - Query todos with filters (status, due date, tags, etc.)
- ``get_project_stats`` - Get completion rates and statistics for notebooks
- ``get_calendar_events`` - Read calendar events (requires Outlook on Windows)

*Write Tools (queued for confirmation):*

- ``create_todo`` - Add a new todo to a note (defaults to today's daily note)
- ``update_todo`` - Change todo status, due date, or delete it
- ``create_note`` - Create a new note
- ``append_to_note`` - Append content to an existing note

**Examples:**

.. code-block:: bash

   # Start interactive assistant
   nb assistant

   # Start with an initial query
   nb assistant "add 3 todos for the quarterly review"

   # Include a file as context
   nb assistant -f plan.md "Review this plan and add todos"

   # Include clipboard content
   nb assistant --paste "Here's my plan for today"

   # Include specific notes as context
   nb assistant -N work/project "Summarize the current status"

   # Include multiple notes
   nb assistant -N work/roadmap -N daily/today "Cross-reference these"

   # Focus on work notebook
   nb assistant -n work

   # Preview changes without executing (dry run)
   nb assistant --dry-run

   # Use faster/cheaper model
   nb assistant --fast

**Example Interactions:**

.. code-block:: text

   You: reschedule the todos for later this week to monday next week

   Assistant: I'll reschedule those todos for you.

   ===== Proposed Changes =====

   [1] UPDATE TODO abc123
       Due date: 2025-12-19 -> 2025-12-23

   [2] UPDATE TODO def456
       Due date: 2025-12-20 -> 2025-12-23

   =============================
   Apply changes? [y]es / [n]o / [1,2,3] select: y

   2 action(s) completed successfully.

.. code-block:: text

   You: analyze the meeting notes from today and add any action items as todos

   Assistant: I found 3 action items in today's meeting notes.

   ===== Proposed Changes =====

   [1] ADD TODO to daily/2025-12-21.md
       - [ ] Follow up with client about proposal @due(2025-12-23)

   [2] ADD TODO to daily/2025-12-21.md
       - [ ] Review API documentation @due(2025-12-24)

   [3] ADD TODO to daily/2025-12-21.md
       - [ ] Schedule team sync @due(2025-12-22)

   =============================
   Apply changes? [y]es / [n]o / [1,2,3] select:

**Confirmation Options:**

- Type ``y`` or ``yes`` to apply all proposed changes
- Type ``n`` or ``no`` to discard all changes
- Type numbers like ``1,2`` to apply only selected changes
- Type ``clear`` to discard pending actions without exiting
- Type ``done``, ``quit``, or ``q`` to exit the assistant

**Session Commands:**

While in the assistant, you can use these commands:

- ``done`` / ``quit`` / ``exit`` / ``q`` - End the session
- ``clear`` - Discard all pending actions

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
