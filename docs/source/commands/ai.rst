AI Commands
===========

AI-powered commands for intelligent note analysis and question answering.

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
