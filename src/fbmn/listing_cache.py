import os
from typing import Set

class Cache:
    def __init__(self, cache_file_path: str):
        """
        Initializes the Cache.

        Args:
            cache_file_path (str): The path to the text cache file.
        """
        self.cache_file_path = cache_file_path
        self.urls: Set[str] = set()
        self._load_cache()  # Try to load existing cache on startup
        print(f"Cache initialized with file: {self.cache_file_path}")

    def _load_cache(self):
        """
        Tries to load URLs from the text cache file (one URL per line).
        If the file doesn't exist, initializes an empty set.
        """
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, "r", encoding="utf-8") as f:
                    self.urls = {line.strip() for line in f if line.strip()}
                print(
                    f"Cache loaded successfully from {self.cache_file_path}. "
                    f"{len(self.urls)} URLs found."
                )
            except IOError as e:
                print(
                    f"Error loading cache from {self.cache_file_path}: {e}. "
                    f"Starting with an empty cache."
                )
                self.urls = set()
        else:
            print(
                f"Cache file not found at {self.cache_file_path}. "
                "Starting with an empty cache."
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
            print(f"Cache saved to {self.cache_file_path}. {len(self.urls)} URLs.")
        except IOError as e:
            print(f"Error saving cache to {self.cache_file_path}: {e}")

    def add_url(self, url: str):
        """
        Adds a URL to the cache.
        """
        self.urls.add(url.strip())

    def contains(self, url: str) -> bool:
        """
        Checks if a URL is already in the cache.
        """
        print("Searching for url in cache:", url)
        in_cache = url.strip() in self.urls
        print(in_cache)
        return in_cache

    def flush(self, x: int):
        """
        Removes the first x lines (URLs) from the cache file 
        and updates the in-memory cache set.

        Args:
            x (int): Number of lines to remove from the beginning of the file.
        """
        if x <= 0:
            print("Flush amount must be greater than 0.")
            return

        if not os.path.exists(self.cache_file_path):
            print("Cache file does not exist. Nothing to flush.")
            return

        try:
            with open(self.cache_file_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]

            if not lines:
                print("Cache file is empty. Nothing to flush.")
                return

            # Drop the first x lines
            remaining = lines[x:]

            # Rewrite the file with remaining URLs
            with open(self.cache_file_path, "w", encoding="utf-8") as f:
                for url in remaining:
                    f.write(url + "\n")

            # Update the in-memory set
            self.urls = set(remaining)

            print(
                f"Flushed {min(x, len(lines))} lines from cache. "
                f"{len(self.urls)} URLs remain."
            )
        except IOError as e:
            print(f"Error flushing cache: {e}")