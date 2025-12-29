"""Raindrop.io API integration for nb inbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from nb.config import get_config

# Raindrop API constants
BASE_URL = "https://api.raindrop.io/rest/v1"
ARCHIVE_COLLECTION_ID = -99  # Special ID for "Archive" collection
UNSORTED_COLLECTION_ID = -1  # Special ID for "Unsorted" collection


class RaindropAuthError(Exception):
    """Raised when Raindrop API authentication fails."""

    pass


class RaindropAPIError(Exception):
    """Raised when Raindrop API returns an error."""

    pass


@dataclass
class RaindropItem:
    """A bookmark item from Raindrop.io."""

    id: int
    url: str
    title: str
    excerpt: str | None
    tags: list[str]
    created: datetime
    collection_id: int
    collection_name: str | None = None
    cover: str | None = None  # Thumbnail URL
    note: str | None = None  # User's note on the bookmark

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> RaindropItem:
        """Create a RaindropItem from API response data."""
        # Parse created date (ISO format)
        created_str = data.get("created", "")
        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created = datetime.now()

        return cls(
            id=data["_id"],
            url=data.get("link", ""),
            title=data.get("title", "Untitled"),
            excerpt=data.get("excerpt") or None,
            tags=data.get("tags", []),
            created=created,
            collection_id=data.get("collection", {}).get("$id", UNSORTED_COLLECTION_ID),
            collection_name=None,  # Filled in separately if needed
            cover=data.get("cover") or None,
            note=data.get("note") or None,
        )


class RaindropClient:
    """Client for interacting with the Raindrop.io API."""

    def __init__(self, api_token: str | None = None):
        """Initialize the Raindrop client.

        Args:
            api_token: Raindrop API token. If not provided, reads from config.
        """
        if api_token is None:
            config = get_config()
            api_token = config.inbox.raindrop.api_token

        if not api_token:
            raise RaindropAuthError(
                "Raindrop API token not configured. "
                "Set RAINDROP_API_KEY environment variable or configure in settings."
            )

        self.api_token = api_token
        self._collections_cache: dict[int, str] | None = None

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an API request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            json: JSON body for POST/PUT requests
            params: Query parameters

        Returns:
            API response as dict

        Raises:
            RaindropAuthError: If authentication fails
            RaindropAPIError: If API returns an error
        """
        url = f"{BASE_URL}{endpoint}"

        with httpx.Client(timeout=30) as client:
            response = client.request(
                method,
                url,
                headers=self._get_headers(),
                json=json,
                params=params,
            )

            if response.status_code == 401:
                raise RaindropAuthError("Invalid or expired API token")
            elif response.status_code == 403:
                raise RaindropAuthError("API token lacks required permissions")
            elif response.status_code >= 400:
                raise RaindropAPIError(
                    f"API error {response.status_code}: {response.text}"
                )

            return response.json()

    def get_collections(self) -> dict[int, str]:
        """Get all collections and their names.

        Returns:
            Dict mapping collection ID to collection name
        """
        if self._collections_cache is not None:
            return self._collections_cache

        # Get root collections
        data = self._request("GET", "/collections")
        collections = {c["_id"]: c["title"] for c in data.get("items", [])}

        # Get child collections
        data = self._request("GET", "/collections/childrens")
        for c in data.get("items", []):
            collections[c["_id"]] = c["title"]

        # Add special collections
        collections[ARCHIVE_COLLECTION_ID] = "Archive"
        collections[UNSORTED_COLLECTION_ID] = "Unsorted"

        self._collections_cache = collections
        return collections

    def get_collection_id(self, name: str) -> int | None:
        """Get collection ID by name.

        Args:
            name: Collection name to find

        Returns:
            Collection ID or None if not found
        """
        collections = self.get_collections()
        name_lower = name.lower()

        for cid, cname in collections.items():
            if cname.lower() == name_lower:
                return cid

        return None

    def list_items(
        self,
        collection_id: int | None = None,
        collection_name: str | None = None,
        limit: int = 50,
        page: int = 0,
    ) -> list[RaindropItem]:
        """List bookmarks from a collection.

        Args:
            collection_id: Collection ID to list from (use -1 for Unsorted)
            collection_name: Collection name to find and list from
            limit: Maximum items to return (max 50 per page)
            page: Page number (0-indexed)

        Returns:
            List of RaindropItem objects
        """
        # Resolve collection name to ID if needed
        if collection_id is None and collection_name:
            collection_id = self.get_collection_id(collection_name)
            if collection_id is None:
                raise RaindropAPIError(f"Collection not found: {collection_name}")
        elif collection_id is None:
            collection_id = UNSORTED_COLLECTION_ID

        # Get items from collection
        data = self._request(
            "GET",
            f"/raindrops/{collection_id}",
            params={"perpage": min(limit, 50), "page": page},
        )

        items = []
        collections = self.get_collections()

        for item_data in data.get("items", []):
            item = RaindropItem.from_api_response(item_data)
            # Fill in collection name
            item.collection_name = collections.get(item.collection_id)
            items.append(item)

        return items

    def archive_item(self, item_id: int) -> bool:
        """Move an item to the Archive collection.

        Args:
            item_id: The raindrop ID to archive

        Returns:
            True if successful
        """
        self._request(
            "PUT",
            f"/raindrop/{item_id}",
            json={"collection": {"$id": ARCHIVE_COLLECTION_ID}},
        )
        return True

    def delete_item(self, item_id: int) -> bool:
        """Permanently delete an item.

        Args:
            item_id: The raindrop ID to delete

        Returns:
            True if successful
        """
        self._request("DELETE", f"/raindrop/{item_id}")
        return True

    def move_item(self, item_id: int, collection_id: int) -> bool:
        """Move an item to a different collection.

        Args:
            item_id: The raindrop ID to move
            collection_id: Target collection ID

        Returns:
            True if successful
        """
        self._request(
            "PUT",
            f"/raindrop/{item_id}",
            json={"collection": {"$id": collection_id}},
        )
        return True

    def get_item(self, item_id: int) -> RaindropItem | None:
        """Get a single item by ID.

        Args:
            item_id: The raindrop ID to fetch

        Returns:
            RaindropItem or None if not found
        """
        try:
            data = self._request("GET", f"/raindrop/{item_id}")
            if "item" in data:
                item = RaindropItem.from_api_response(data["item"])
                # Fill in collection name
                collections = self.get_collections()
                item.collection_name = collections.get(item.collection_id)
                return item
        except RaindropAPIError:
            return None
        return None


# Convenience functions using default client
def list_inbox_items(
    collection: str | None = None,
    limit: int = 50,
) -> list[RaindropItem]:
    """List items from the configured inbox collection.

    Args:
        collection: Collection name (defaults to config inbox.raindrop.collection)
        limit: Maximum items to return

    Returns:
        List of RaindropItem objects
    """
    config = get_config()
    if collection is None:
        collection = config.inbox.raindrop.collection

    client = RaindropClient()
    return client.list_items(collection_name=collection, limit=limit)


def archive_item(item_id: int) -> bool:
    """Archive an item in Raindrop.

    Args:
        item_id: The raindrop ID to archive

    Returns:
        True if successful
    """
    client = RaindropClient()
    return client.archive_item(item_id)


def delete_item(item_id: int) -> bool:
    """Delete an item from Raindrop.

    Args:
        item_id: The raindrop ID to delete

    Returns:
        True if successful
    """
    client = RaindropClient()
    return client.delete_item(item_id)


# Inbox tracking functions (database operations)
def _get_db():
    """Get database connection."""
    from nb.index.db import get_db

    return get_db()


def is_item_clipped(item_id: int | str, source: str = "raindrop") -> bool:
    """Check if an item has already been clipped.

    Args:
        item_id: External service item ID
        source: Source service name

    Returns:
        True if the item was already clipped
    """
    db = _get_db()
    row = db.fetchone(
        "SELECT clipped_at FROM inbox_items WHERE id = ? AND source = ?",
        (str(item_id), source),
    )
    return row is not None and row["clipped_at"] is not None


def get_clipped_item(item_id: int | str, source: str = "raindrop") -> dict | None:
    """Get info about a previously clipped item.

    Args:
        item_id: External service item ID
        source: Source service name

    Returns:
        Dict with clipped item info or None if not found
    """
    db = _get_db()
    row = db.fetchone(
        """SELECT id, source, url, title, clipped_at, note_path, archived, skipped
           FROM inbox_items WHERE id = ? AND source = ?""",
        (str(item_id), source),
    )
    if row:
        return dict(row)
    return None


def record_clipped_item(
    item_id: int | str,
    url: str,
    title: str | None,
    note_path: str | None,
    source: str = "raindrop",
    archived: bool = False,
    skipped: bool = False,
    raindrop_tags: list[str] | None = None,
    raindrop_note: str | None = None,
    collection_name: str | None = None,
) -> None:
    """Record that an item has been clipped.

    Args:
        item_id: External service item ID
        url: Original URL of the bookmark
        title: Title of the bookmark
        note_path: Path to the note where content was clipped
        source: Source service name
        archived: Whether the item was archived in the source service
        skipped: Whether the item was skipped
        raindrop_tags: Original tags from Raindrop (for sync detection)
        raindrop_note: Original note from Raindrop (for sync detection)
        collection_name: Source collection name
    """
    import json
    from datetime import datetime

    db = _get_db()
    now = datetime.now().isoformat()

    with db.transaction():
        # Use INSERT OR REPLACE to update if exists
        db.execute(
            """INSERT OR REPLACE INTO inbox_items
               (id, source, url, title, clipped_at, note_path, archived, skipped, created_at,
                raindrop_tags, raindrop_note, collection_name, last_synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(item_id),
                source,
                url,
                title,
                now if not skipped else None,
                note_path,
                1 if archived else 0,
                1 if skipped else 0,
                now,
                json.dumps(raindrop_tags) if raindrop_tags else None,
                raindrop_note,
                collection_name,
                now,
            ),
        )


def list_clipped_items(
    source: str = "raindrop",
    limit: int = 50,
    include_skipped: bool = False,
) -> list[dict]:
    """List previously clipped items.

    Args:
        source: Source service name
        limit: Maximum items to return
        include_skipped: Include skipped items

    Returns:
        List of dicts with clipped item info
    """
    db = _get_db()

    if include_skipped:
        query = """SELECT id, source, url, title, clipped_at, note_path, archived, skipped
                   FROM inbox_items WHERE source = ?
                   ORDER BY clipped_at DESC LIMIT ?"""
    else:
        query = """SELECT id, source, url, title, clipped_at, note_path, archived, skipped
                   FROM inbox_items WHERE source = ? AND skipped = 0
                   ORDER BY clipped_at DESC LIMIT ?"""

    rows = db.fetchall(query, (source, limit))
    return [dict(row) for row in rows]


def get_duplicate_warning(url: str, source: str = "raindrop") -> str | None:
    """Check if a URL was previously clipped and return warning message.

    Args:
        url: URL to check
        source: Source service name

    Returns:
        Warning message if duplicate, None otherwise
    """
    db = _get_db()
    row = db.fetchone(
        """SELECT title, note_path, clipped_at FROM inbox_items
           WHERE url = ? AND source = ? AND clipped_at IS NOT NULL""",
        (url, source),
    )
    if row:
        note = row["note_path"] or "unknown note"
        return f"Already clipped to {note} on {row['clipped_at'][:10]}"
    return None


def get_items_needing_sync(
    source: str = "raindrop",
    limit: int = 100,
) -> list[dict]:
    """Get clipped items that may need tag/note sync.

    Returns items that:
    - Were successfully clipped (not skipped)
    - Have a note_path (local note exists)

    Args:
        source: Source service name
        limit: Maximum items to return

    Returns:
        List of dicts with item info for sync
    """
    db = _get_db()
    rows = db.fetchall(
        """SELECT id, url, note_path, raindrop_tags, raindrop_note, collection_name
           FROM inbox_items
           WHERE source = ?
             AND skipped = 0
             AND note_path IS NOT NULL
           ORDER BY last_synced_at ASC
           LIMIT ?""",
        (source, limit),
    )
    return [dict(row) for row in rows]


def update_sync_metadata(
    item_id: int | str,
    raindrop_tags: list[str] | None,
    raindrop_note: str | None,
    source: str = "raindrop",
) -> None:
    """Update the sync metadata for an item after sync.

    Args:
        item_id: External service item ID
        raindrop_tags: Current tags from Raindrop
        raindrop_note: Current note from Raindrop
        source: Source service name
    """
    import json
    from datetime import datetime

    db = _get_db()
    now = datetime.now().isoformat()

    db.execute(
        """UPDATE inbox_items
           SET raindrop_tags = ?, raindrop_note = ?, last_synced_at = ?
           WHERE id = ? AND source = ?""",
        (
            json.dumps(raindrop_tags) if raindrop_tags else None,
            raindrop_note,
            now,
            str(item_id),
            source,
        ),
    )
    db.commit()
