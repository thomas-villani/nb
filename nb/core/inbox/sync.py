"""Sync logic for Raindrop tags and notes to local notes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from nb.config import get_config
from nb.core.inbox.raindrop import (
    RaindropClient,
    get_items_needing_sync,
    update_sync_metadata,
)


@dataclass
class SyncResult:
    """Result of syncing a single item."""

    item_id: str
    note_path: str
    tags_updated: bool = False
    note_updated: bool = False
    error: str | None = None
    old_tags: list[str] = field(default_factory=list)
    new_tags: list[str] = field(default_factory=list)


def sync_item_tags(
    note_path: Path,
    old_raindrop_tags: list[str],
    new_raindrop_tags: list[str],
) -> bool:
    """Sync tags from Raindrop to a local note.

    Strategy: Only update tags that came from Raindrop.
    - Tags in old_raindrop_tags but not new_raindrop_tags: remove from note
    - Tags in new_raindrop_tags but not old_raindrop_tags: add to note
    - User-added tags (not in old_raindrop_tags): preserve

    Args:
        note_path: Path to the local note
        old_raindrop_tags: Tags from Raindrop at last sync
        new_raindrop_tags: Current tags from Raindrop

    Returns:
        True if note was modified
    """
    if not note_path.exists():
        return False

    # Load note with frontmatter
    with note_path.open(encoding="utf-8") as f:
        post = frontmatter.load(f)

    # Get current note tags
    current_tags = set(post.metadata.get("tags", []))
    old_rd_tags = set(old_raindrop_tags)
    new_rd_tags = set(new_raindrop_tags)

    # Calculate what changed in Raindrop
    tags_removed_in_raindrop = old_rd_tags - new_rd_tags
    tags_added_in_raindrop = new_rd_tags - old_rd_tags

    # If nothing changed in Raindrop, no update needed
    if not tags_removed_in_raindrop and not tags_added_in_raindrop:
        return False

    # Apply changes:
    # - Remove tags that were removed in Raindrop
    # - Add tags that were added in Raindrop
    # - Keep all other tags (user-added tags are preserved)
    final_tags = (current_tags - tags_removed_in_raindrop) | tags_added_in_raindrop

    if final_tags == current_tags:
        return False  # No actual changes needed

    # Update note
    post.metadata["tags"] = sorted(final_tags)
    with note_path.open("w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    return True


# Markers for Raindrop note section
RAINDROP_NOTE_START = "<!-- raindrop-note-start -->"
RAINDROP_NOTE_END = "<!-- raindrop-note-end -->"


def sync_item_note(
    note_path: Path,
    old_note: str | None,
    new_note: str | None,
) -> bool:
    """Sync Raindrop note content to local note.

    The Raindrop note is stored as a blockquote section with HTML comment markers.

    Args:
        note_path: Path to the local note
        old_note: Note content at last sync
        new_note: Current note content from Raindrop

    Returns:
        True if note was modified
    """
    # Normalize empty strings to None for comparison
    old_note = old_note.strip() if old_note else None
    new_note = new_note.strip() if new_note else None

    if old_note == new_note:
        return False

    if not note_path.exists():
        return False

    content = note_path.read_text(encoding="utf-8")

    # Build the new note section (or empty if note was removed)
    if new_note:
        new_section = f"{RAINDROP_NOTE_START}\n\n> **Raindrop Note:** {new_note}\n\n{RAINDROP_NOTE_END}"
    else:
        new_section = ""

    if RAINDROP_NOTE_START in content:
        # Replace existing section
        pattern = f"{re.escape(RAINDROP_NOTE_START)}.*?{re.escape(RAINDROP_NOTE_END)}"
        content = re.sub(pattern, new_section, content, flags=re.DOTALL)
    elif new_note:
        # Insert new section after [Original source] link
        source_pattern = r"(\[Original source\]\([^)]+\)\n)"
        if re.search(source_pattern, content):
            replacement = f"\\1\n{new_section}\n"
            content = re.sub(source_pattern, replacement, content, count=1)
        else:
            # Fallback: insert after frontmatter
            # Find end of frontmatter (second ---)
            frontmatter_end = content.find("---", content.find("---") + 3)
            if frontmatter_end != -1:
                insert_pos = content.find("\n", frontmatter_end) + 1
                content = (
                    content[:insert_pos] + f"\n{new_section}\n" + content[insert_pos:]
                )

    note_path.write_text(content, encoding="utf-8")
    return True


def sync_clipped_items(
    limit: int = 50,
    dry_run: bool = False,
) -> list[SyncResult]:
    """Sync tags and notes for previously clipped items.

    Fetches current metadata from Raindrop for each clipped item
    and updates local notes if tags or notes have changed.

    Args:
        limit: Max items to sync
        dry_run: If True, don't modify notes (just report what would change)

    Returns:
        List of SyncResult objects
    """
    config = get_config()
    results: list[SyncResult] = []

    # Check if sync is enabled
    raindrop_config = config.inbox.raindrop
    if not raindrop_config.sync_tags and not raindrop_config.sync_notes:
        return results

    # Get items that might need sync
    items = get_items_needing_sync(limit=limit)

    if not items:
        return results

    client = RaindropClient()

    for item in items:
        item_id = item["id"]
        rel_note_path = item["note_path"]
        note_path = config.notes_root / rel_note_path if rel_note_path else None
        old_tags = json.loads(item["raindrop_tags"] or "[]")
        old_note = item["raindrop_note"]

        result = SyncResult(
            item_id=item_id,
            note_path=rel_note_path or "",
            old_tags=old_tags,
        )

        if not note_path or not note_path.exists():
            result.error = "Note file not found"
            results.append(result)
            continue

        try:
            # Fetch current item from Raindrop
            raindrop_item = client.get_item(int(item_id))

            if raindrop_item is None:
                result.error = "Item not found in Raindrop (may have been deleted)"
                results.append(result)
                continue

            new_tags = raindrop_item.tags
            new_note = raindrop_item.note
            result.new_tags = new_tags

            # Sync tags
            if raindrop_config.sync_tags:
                if dry_run:
                    # Check if tags would change
                    old_set = set(old_tags)
                    new_set = set(new_tags)
                    result.tags_updated = old_set != new_set
                else:
                    result.tags_updated = sync_item_tags(note_path, old_tags, new_tags)

            # Sync note
            if raindrop_config.sync_notes:
                if dry_run:
                    # Check if note would change
                    old_normalized = old_note.strip() if old_note else None
                    new_normalized = new_note.strip() if new_note else None
                    result.note_updated = old_normalized != new_normalized
                else:
                    result.note_updated = sync_item_note(note_path, old_note, new_note)

            # Update metadata in database
            if not dry_run and (result.tags_updated or result.note_updated):
                update_sync_metadata(item_id, new_tags, new_note)

                # Re-index the note
                try:
                    from nb.core.notes import _reindex_note_after_edit

                    _reindex_note_after_edit(note_path, config.notes_root)
                except Exception:
                    pass  # Non-fatal: note still updated, just not re-indexed

        except Exception as e:
            result.error = str(e)

        results.append(result)

    return results
