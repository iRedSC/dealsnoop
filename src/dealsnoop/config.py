"""Shared configuration loaded from environment."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Path prefix for data files (searches, caches). Empty string = current directory.
FILE_PATH: str = os.getenv("FILE_PATH") or ""

# Discord guild ID for slash command registration.
GUILD_ID: int = 1411757356894650381

# Default channel ID when none provided in /watch command.
DEFAULT_CHANNEL_ID: int = 1412121636815241397
