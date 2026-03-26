"""Meeting notes generation from transcripts using LLM post-processing."""

from __future__ import annotations

from rich.console import Console

MEETING_NOTES_SYSTEM_PROMPT = """\
You are a meeting notes assistant. Given a meeting transcript, generate concise, \
well-organized meeting notes in markdown format.

Include the following sections as applicable:
- **Summary**: 2-3 sentence overview of the meeting
- **Key Discussion Points**: Bullet points of the main topics discussed
- **Decisions Made**: Any decisions that were reached
- **Action Items**: Tasks assigned during the meeting, with assignees if mentioned
- **Follow-ups**: Items that need further discussion or investigation

Be concise and focus on the most important information. Skip sections that have no \
content. Use bullet points for readability. Do not include a top-level heading."""

console = Console()


def generate_meeting_notes(transcript_text: str) -> str | None:
    """Generate meeting notes from a transcript using an LLM.

    Uses the fast model (Haiku) for cost-effective summarization.

    Args:
        transcript_text: The full transcript text.

    Returns:
        Formatted meeting notes in markdown, or None if LLM is not configured
        or an error occurs.
    """
    from nb.core.llm import LLMAPIError, LLMConfigError, Message, get_llm_client

    try:
        client = get_llm_client()
    except LLMConfigError:
        console.print(
            "[dim]Skipping meeting notes: LLM not configured "
            "(set ANTHROPIC_API_KEY or OPENAI_API_KEY)[/dim]"
        )
        return None

    console.print("[cyan]Generating meeting notes...[/cyan]")

    try:
        response = client.complete(
            messages=[
                Message(
                    role="user",
                    content=(
                        "Generate meeting notes from this transcript:\n\n"
                        + transcript_text
                    ),
                )
            ],
            system=MEETING_NOTES_SYSTEM_PROMPT,
            use_smart_model=False,  # Use fast model (Haiku)
            max_tokens=2048,
            temperature=0.3,
        )
        return response.content
    except LLMAPIError as e:
        console.print(f"[yellow]Meeting notes generation failed: {e}[/yellow]")
        return None
