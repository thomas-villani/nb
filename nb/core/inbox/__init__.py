"""Inbox module for pulling bookmarks from external services."""

from __future__ import annotations

from nb.core.inbox.raindrop import (
    RaindropAPIError,
    RaindropAuthError,
    RaindropClient,
    RaindropItem,
    archive_item,
    delete_item,
    get_clipped_item,
    get_duplicate_warning,
    get_items_needing_sync,
    is_item_clipped,
    list_clipped_items,
    list_inbox_items,
    record_clipped_item,
    update_sync_metadata,
)
from nb.core.inbox.sync import (
    SyncResult,
    sync_clipped_items,
    sync_item_note,
    sync_item_tags,
)

__all__ = [
    "RaindropAPIError",
    "RaindropAuthError",
    "RaindropClient",
    "RaindropItem",
    "SyncResult",
    "archive_item",
    "delete_item",
    "get_clipped_item",
    "get_duplicate_warning",
    "get_items_needing_sync",
    "is_item_clipped",
    "list_clipped_items",
    "list_inbox_items",
    "record_clipped_item",
    "sync_clipped_items",
    "sync_item_note",
    "sync_item_tags",
    "update_sync_metadata",
]
