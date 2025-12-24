#!/usr/bin/env python3
"""Capture real API responses for golden file tests.

This script makes real API calls and saves the responses to the
tests/fixtures directory. Run it periodically to update golden files
when APIs change.

Usage:
    python scripts/capture_api_responses.py [--all] [--anthropic] [--openai] [--serper]

Requirements:
    - ANTHROPIC_API_KEY for Anthropic responses
    - OPENAI_API_KEY for OpenAI responses
    - SERPER_API_KEY for Serper responses
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

FIXTURES_DIR = project_root / "tests" / "fixtures"


def capture_anthropic_response():
    """Capture a real Anthropic API response."""
    import httpx

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set, skipping Anthropic capture")
        return

    print("Capturing Anthropic response...")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    # Simple completion
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Say hello and introduce yourself briefly."}],
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
        )

        if response.status_code == 200:
            data = response.json()
            with (FIXTURES_DIR / "anthropic_response.json").open("w") as f:
                json.dump(data, f, indent=2)
            print("  Saved anthropic_response.json")
        else:
            print(f"  Error: {response.status_code} - {response.text}")

    # Tool-use completion
    body_tools = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": "Search for budget meeting notes."}],
        "tools": [
            {
                "name": "search_notes",
                "description": "Search notes by query",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "description": "Max results"},
                    },
                    "required": ["query"],
                },
            }
        ],
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body_tools,
        )

        if response.status_code == 200:
            data = response.json()
            with (FIXTURES_DIR / "anthropic_tool_response.json").open("w") as f:
                json.dump(data, f, indent=2)
            print("  Saved anthropic_tool_response.json")
        else:
            print(f"  Error: {response.status_code} - {response.text}")


def capture_openai_response():
    """Capture a real OpenAI API response."""
    import httpx

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set, skipping OpenAI capture")
        return

    print("Capturing OpenAI response...")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "gpt-4o-mini",
        "max_tokens": 100,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello and introduce yourself briefly."},
        ],
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=body,
        )

        if response.status_code == 200:
            data = response.json()
            with (FIXTURES_DIR / "openai_response.json").open("w") as f:
                json.dump(data, f, indent=2)
            print("  Saved openai_response.json")
        else:
            print(f"  Error: {response.status_code} - {response.text}")


def capture_serper_response():
    """Capture a real Serper API response."""
    import httpx

    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("SERPER_API_KEY not set, skipping Serper capture")
        return

    print("Capturing Serper response...")

    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    body = {
        "q": "python pytest best practices",
        "num": 5,
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            "https://google.serper.dev/search",
            headers=headers,
            json=body,
        )

        if response.status_code == 200:
            data = response.json()
            with (FIXTURES_DIR / "serper_web_response.json").open("w") as f:
                json.dump(data, f, indent=2)
            print("  Saved serper_web_response.json")
        else:
            print(f"  Error: {response.status_code} - {response.text}")


def main():
    parser = argparse.ArgumentParser(description="Capture API responses for golden file tests")
    parser.add_argument("--all", action="store_true", help="Capture all API responses")
    parser.add_argument("--anthropic", action="store_true", help="Capture Anthropic responses")
    parser.add_argument("--openai", action="store_true", help="Capture OpenAI responses")
    parser.add_argument("--serper", action="store_true", help="Capture Serper responses")

    args = parser.parse_args()

    # If no specific flags, capture all
    if not any([args.anthropic, args.openai, args.serper]):
        args.all = True

    # Ensure fixtures directory exists
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Saving responses to: {FIXTURES_DIR}\n")

    if args.all or args.anthropic:
        capture_anthropic_response()

    if args.all or args.openai:
        capture_openai_response()

    if args.all or args.serper:
        capture_serper_response()

    print("\nDone!")


if __name__ == "__main__":
    main()
