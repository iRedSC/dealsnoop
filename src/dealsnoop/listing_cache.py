"""URL cache for avoiding duplicate listing notifications."""

import os
from typing import TYPE_CHECKING, Set

from dealsnoop.logger import logger

if TYPE_CHECKING:
    from dealsnoop.store import SearchStore


class Cache:
    """File-based cache (legacy)."""

    def __init__(self, cache_file_path: str):
        """
        Initializes the Cache.

        Args:
            cache_file_path (str): The path to the text cache file.
        """
        self.cache_file_path = cache_file_path
        self.urls: Set[str] = set()
        self._load_cache()  # Try to load existing cache on startup
        logger.info(f"Cache initialized with file: $B${self.cache_file_path}")

    def _load_cache(self):
        """
        Tries to load URLs from the text cache file (one URL per line).
        If the file doesn't exist, initializes an empty set.
        """
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, "r", encoding="utf-8") as f:
                    self.urls = {line.strip() for line in f if line.strip()}
                logger.info(
                    f"Cache loaded successfully from {self.cache_file_path}. "
                    f"{len(self.urls)} URLs found."
                )
            except IOError as e:
                logger.info(
                    f"Error loading cache from {self.cache_file_path}: {e}. "
                    f"Starting with an empty cache."
                )
                self.urls = set()
        else:
            logger.info(
                f"Cache file not found at {self.cache_file_path}. "
                "Starting with empty cache."
            )
            self.urls = set()

    def save_cache(self):
        """
        Saves the current URL set to the cache file, one URL per line.
        You must call this explicitly to save changes.
        """
        try:
            with open(self.cache_file_path, "w", encoding="utf-8") as f:
                for url in self.urls:
                    f.write(url + "\n")
            logger.info(f"Cache saved to $M${self.cache_file_path}$W$. {len(self.urls)} URLs.")
        except IOError as e:
            logger.info(f"Error saving cache to $M${self.cache_file_path}$W$: $B${e}")

    def add_url(self, url: str):
        """
        Adds a URL to the cache.
        """
        self.urls.add(url.strip())

    def contains(self, url: str) -> bool:
        """Check if a URL is already in the cache."""
        return url.strip() in self.urls

    def clear(self):
        """Clears all URLs from the cache (in-memory and on disk)."""
        self.urls.clear()
        self.save_cache()
        logger.info(f"Cache cleared: $M${self.cache_file_path}$W$")

    def flush_old_entries(self) -> int:
        """No-op for file-based cache; age-based flush is DB-only."""
        return 0

    def flush(self, x: int):
        """
        Removes the first x lines (URLs) from the cache file
        and updates the in-memory cache set.

        Args:
            x (int): Number of lines to remove from the beginning of the file.
        """
        if x <= 0:
            logger.warning("$Y$Flush amount must be greater than 0.")
            return

        if not os.path.exists(self.cache_file_path):
            logger.error("$R$Cache file does not exist. Nothing to flush.")
            return

        try:
            with open(self.cache_file_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]

            if not lines:
                logger.info("Cache file is empty. Nothing to flush.")
                return

            # Drop the first x lines
            remaining = lines[x:]

            # Rewrite the file with remaining URLs
            with open(self.cache_file_path, "w", encoding="utf-8") as f:
                for url in remaining:
                    f.write(url + "\n")

            # Update the in-memory set
            self.urls = set(remaining)

            logger.info(
                f"Flushed {min(x, len(lines))} lines from cache. "
                f"{len(self.urls)} URLs remain."
            )
        except IOError as e:
            logger.error(f"Error flushing cache: {e}")


class DbCache:
    """Database-backed cache that persists across restarts and flushes entries older than 2 days."""

    def __init__(self, store: "SearchStore", engine: str, max_age_days: int = 2):
        self._store = store
        self._engine = engine
        self._max_age_days = max_age_days
        logger.info(f"DbCache initialized for engine: $B${engine}")

    def add_url(self, url: str) -> None:
        """Add a listing ID to the cache."""
        self._store.listing_cache_add(self._engine, url)

    def contains(self, url: str) -> bool:
        """Check if a listing ID is already in the cache."""
        return self._store.listing_cache_contains(self._engine, url)

    def save_cache(self) -> None:
        """No-op for DB cache; each add is persisted immediately."""
        pass

    def clear(self) -> None:
        """Clear all entries from the cache for this engine."""
        count = self._store.listing_cache_clear(self._engine)
        logger.info(f"Cache cleared for engine $M${self._engine}$W$: {count} entries removed.")

    def flush_old_entries(self) -> int:
        """Remove entries older than max_age_days. Returns number removed."""
        removed = self._store.listing_cache_flush_older_than_days(
            self._engine, self._max_age_days
        )
        if removed:
            logger.info(
                f"Flushed {removed} cache entries older than {self._max_age_days} days "
                f"for engine $M${self._engine}$W$"
            )
        return removed
