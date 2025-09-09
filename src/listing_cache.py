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
        self._load_cache() # Try to load existing cache on startup
        print(f"Cache initialized with file: {self.cache_file_path}")

    def _load_cache(self):
        """
        Tries to load URLs from the text cache file (one URL per line).
        If the file doesn't exist, initializes an empty set.
        """
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                    # Read each line, strip whitespace (like newlines), and add to set
                    self.urls = {line.strip() for line in f if line.strip()}
                print(f"Cache loaded successfully from {self.cache_file_path}. "
                      f"{len(self.urls)} URLs found.")
            except IOError as e:
                print(f"Error loading cache from {self.cache_file_path}: {e}. "
                      f"Starting with an empty cache.")
                self.urls = set() # Start with empty set if load fails
        else:
            print(f"Cache file not found at {self.cache_file_path}. Starting with an empty cache.")
            self.urls = set() # Start with empty set if file doesn't exist

    def save_cache(self):
        """
        Saves the current URL set to the cache file, one URL per line.
        You must call this explicitly to save changes.
        """
        try:
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                # Write each URL on a new line
                for url in self.urls:
                    f.write(url + '\n')
            print(f"Cache saved to {self.cache_file_path}. {len(self.urls)} URLs.")
        except IOError as e:
            print(f"Error saving cache to {self.cache_file_path}: {e}")

    def add_url(self, url: str):
        """
        Adds a URL to the cache.
        """
        # Ensure URLs are clean before adding to avoid extra whitespace in the set
        self.urls.add(url.strip())

    def contains(self, url: str) -> bool:
        """
        Checks if a URL is already in the cache.
        """
        print("Searching for url in cache: ", url)
        in_cache = url.strip() in self.urls
        print(in_cache)
        return in_cache