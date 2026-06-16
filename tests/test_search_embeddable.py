"""Unit tests for embeddable-text preparation in the search module.

These cover the fallback that prevents sending empty documents (e.g. image-only
notes) to the embeddings API, which otherwise returns a 400 Bad Request.
"""

from pathlib import Path

from nb.index.search import _embeddable_text
from nb.models import Note


def _make_note(title: str = "", name: str = "note.md") -> Note:
    return Note(
        id="abc12345",
        path=Path(name),
        title=title,
        date=None,
        tags=[],
        links=[],
        attachments=[],
        notebook="test",
        content_hash="",
    )


def test_embeddable_text_keeps_real_content():
    note = _make_note(title="My Note")
    content = "# My Note\n\nSome real body text."
    assert _embeddable_text(note, content) == content


def test_embeddable_text_falls_back_to_title_for_image_only_note():
    note = _make_note(title="Scanned Plan")
    content = "![Image from page 1](/abs/path/to/scan_p1_img1.png)"
    # After image stripping the body is empty; fall back to the title.
    assert _embeddable_text(note, content) == "Scanned Plan"


def test_embeddable_text_falls_back_to_filename_when_no_title():
    note = _make_note(title="", name="2023_scan.md")
    content = "![Image](/abs/path/to/img.png)"
    assert _embeddable_text(note, content) == "2023_scan.md"


def test_embeddable_text_falls_back_for_whitespace_only_after_strip():
    note = _make_note(title="Title Here")
    content = "   \n\n  ![x](/p.png)  \n  "
    assert _embeddable_text(note, content) == "Title Here"
