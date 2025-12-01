Installation
============

Requirements
------------

- Python 3.13+
- `Ollama <https://ollama.ai/>`_ (optional, for semantic search)

Install from source
-------------------

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/user/nb-cli.git
   cd nb-cli

   # Install with uv (recommended)
   uv sync

   # Or with pip
   pip install -e .

Verify installation
-------------------

.. code-block:: bash

   nb --version
   nb --help

Setting up semantic search
--------------------------

Semantic search requires Ollama running locally with an embedding model:

.. code-block:: bash

   # Install Ollama from https://ollama.ai/

   # Pull an embedding model
   ollama pull nomic-embed-text

   # Start Ollama (usually runs as a service)
   ollama serve

Configure nb to use it:

.. code-block:: bash

   nb config set embeddings.provider ollama
   nb config set embeddings.model nomic-embed-text

Alternatively, use OpenAI embeddings:

.. code-block:: bash

   nb config set embeddings.provider openai
   nb config set embeddings.api_key sk-your-key-here

Setting up meeting recording
----------------------------

Meeting recording is an optional feature that requires additional dependencies:

.. code-block:: bash

   # Install recorder dependencies
   uv sync --extra recorder

   # Or with pip
   pip install -e ".[recorder]"

**Requirements:**

- Windows with WASAPI-capable audio devices
- Deepgram API key for transcription

Set up your Deepgram API key:

.. code-block:: bash

   # Set environment variable
   export DEEPGRAM_API_KEY=your-api-key-here

   # Or on Windows (PowerShell)
   $env:DEEPGRAM_API_KEY = "your-api-key-here"

Get a Deepgram API key at https://console.deepgram.com/

Test recording is available:

.. code-block:: bash

   nb record devices   # Should list audio devices
   nb record --help    # Show recording commands
