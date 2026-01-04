"""
Tag Manager for Polymarket Gamma API

Handles tag-to-ID mapping and fetching events by tag.
"""
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class Tag:
    """Represents a Polymarket tag"""
    id: str
    label: str
    slug: str
    force_show: bool = False
    published_at: Optional[str] = None


class TagManager:
    """
    Manages Polymarket tags and provides methods to fetch events by tag.

    Usage:
        manager = TagManager()
        crypto_tag = manager.get_tag("crypto")
        events = manager.get_events_by_tag_id(crypto_tag.id, active=True)
    """

    # Common tag slugs for quick reference
    COMMON_TAGS = {
        "crypto": "crypto",
        "politics": "politics",
        "sports": "sports",
        "business": "business",
        "world": "world",
        "technology": "technology",
        "entertainment": "entertainment",
        "science": "science",
        "health": "health",
        "economics": "economics",
    }

    # Cache for tag data
    _tag_cache: Dict[str, Tag] = {}

    def __init__(self, base_url: str = "https://gamma-api.polymarket.com"):
        self.base_url = base_url

    def get_tag(self, slug: str) -> Optional[Tag]:
        """
        Get tag information by slug.

        Args:
            slug: Tag slug (e.g., "crypto", "politics")

        Returns:
            Tag object or None if not found
        """
        # Check cache first
        if slug in self._tag_cache:
            return self._tag_cache[slug]

        try:
            url = f"{self.base_url}/tags/slug/{slug}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                tag = Tag(
                    id=data.get("id", ""),
                    label=data.get("label", ""),
                    slug=data.get("slug", ""),
                    force_show=data.get("forceShow", False),
                    published_at=data.get("publishedAt")
                )
                self._tag_cache[slug] = tag
                return tag
        except Exception as e:
            print(f"Error fetching tag {slug}: {e}")

        return None

    def get_tag_id(self, slug: str) -> Optional[str]:
        """
        Get tag ID by slug.

        Args:
            slug: Tag slug (e.g., "crypto", "politics")

        Returns:
            Tag ID string or None if not found
        """
        tag = self.get_tag(slug)
        return tag.id if tag else None

    def get_all_tags(self) -> List[Tag]:
        """
        Fetch all available tags from the API.

        Returns:
            List of Tag objects
        """
        try:
            url = f"{self.base_url}/tags"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                tags = []
                for item in data:
                    tag = Tag(
                        id=item.get("id", ""),
                        label=item.get("label", ""),
                        slug=item.get("slug", ""),
                        force_show=item.get("forceShow", False),
                        published_at=item.get("publishedAt")
                    )
                    tags.append(tag)
                    # Cache
                    self._tag_cache[tag.slug] = tag
                return tags
        except Exception as e:
            print(f"Error fetching all tags: {e}")

        return []

    def get_events_by_tag_id(
        self,
        tag_id: str,
        active: bool = True,
        limit: int = 100
    ) -> List[Dict]:
        """
        Fetch events by tag ID.

        Args:
            tag_id: Tag ID (e.g., "21" for crypto)
            active: Filter active events only
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        try:
            params = {
                "tag_id": tag_id,
                "limit": limit
            }
            if active is not None:
                params["active"] = str(active).lower()

            url = f"{self.base_url}/events"
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching events for tag {tag_id}: {e}")

        return []

    def get_events_by_tag_slug(
        self,
        slug: str,
        active: bool = True,
        limit: int = 100
    ) -> List[Dict]:
        """
        Fetch events by tag slug (convenience method).

        Args:
            slug: Tag slug (e.g., "crypto", "politics")
            active: Filter active events only
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        tag_id = self.get_tag_id(slug)
        if not tag_id:
            print(f"Tag not found: {slug}")
            return []

        return self.get_events_by_tag_id(tag_id, active=active, limit=limit)

    def get_common_tag_ids(self) -> Dict[str, str]:
        """
        Get a mapping of common tag names to their IDs.

        Returns:
            Dictionary mapping tag slug to tag ID
        """
        result = {}
        for slug in self.COMMON_TAGS.keys():
            tag_id = self.get_tag_id(slug)
            if tag_id:
                result[slug] = tag_id
        return result

    def list_popular_tags(self, limit: int = 20) -> List[Tag]:
        """
        List popular tags (those with force_show=True or commonly used).

        Args:
            limit: Maximum number of tags to return

        Returns:
            List of popular Tag objects
        """
        all_tags = self.get_all_tags()

        # Sort by force_show first, then by label
        sorted_tags = sorted(
            all_tags,
            key=lambda t: (not t.force_show, t.label.lower())
        )

        # Filter out very specific tags (those with numbers or very long names)
        popular = [
            t for t in sorted_tags
            if t.force_show or (len(t.slug) > 3 and not t.slug.isdigit())
        ]

        return popular[:limit]


# Singleton instance for easy access
_default_manager: Optional[TagManager] = None


def get_tag_manager() -> TagManager:
    """Get the default TagManager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = TagManager()
    return _default_manager


if __name__ == "__main__":
    # Test the tag manager
    manager = TagManager()

    print("=== Common Tags ===")
    common_ids = manager.get_common_tag_ids()
    for slug, tag_id in common_ids.items():
        print(f"{slug}: {tag_id}")

    print("\n=== Crypto Events ===")
    crypto_events = manager.get_events_by_tag_slug("crypto", active=True, limit=5)
    print(f"Found {len(crypto_events)} crypto events")
    for event in crypto_events[:2]:
        print(f"- {event.get('title', 'N/A')}")
        print(f"  Markets: {len(event.get('markets', []))}")
