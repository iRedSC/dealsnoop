"""PostgreSQL-backed storage for search configurations."""

from __future__ import annotations

import json
import os

import psycopg
from psycopg.rows import dict_row

from dealsnoop.logger import logger
from dealsnoop.search_config import SearchConfig
from dealsnoop.user_location import UserLocation

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS searches (
    id VARCHAR(255) PRIMARY KEY,
    terms JSONB NOT NULL,
    channel BIGINT NOT NULL,
    city_code VARCHAR(50) NOT NULL DEFAULT '107976589222439',
    location_name TEXT,
    target_price VARCHAR(50),
    days_listed INT NOT NULL DEFAULT 1,
    radius INT NOT NULL DEFAULT 30,
    context TEXT
);
"""

BOT_CONFIG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS bot_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

USER_LOCATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_locations (
    user_id BIGINT PRIMARY KEY,
    city_code VARCHAR(50) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""

LOCATION_CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS location_cache (
    city_code VARCHAR(50) PRIMARY KEY,
    location_name TEXT NOT NULL
);
"""

LISTING_METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS listing_metadata (
    message_id BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    search_id VARCHAR(255) NOT NULL,
    thought_trace TEXT
);
"""


def _row_to_config(row: dict) -> SearchConfig:
    """Convert a database row to SearchConfig."""
    raw = row["terms"]
    terms = tuple(json.loads(raw) if isinstance(raw, str) else raw)
    return SearchConfig(
        id=row["id"],
        terms=terms,
        channel=row["channel"],
        city_code=row["city_code"],
        location_name=row.get("location_name"),
        target_price=row["target_price"],
        days_listed=row["days_listed"],
        radius=row["radius"],
        context=row["context"],
    )


class SearchStore:
    """
    PostgreSQL-backed store for SearchConfig objects.
    Uses DB_URL environment variable for connection.
    """

    def __init__(self) -> None:
        db_url = os.getenv("DB_URL")
        if not db_url:
            raise SystemExit("DB_URL environment variable is required.")
        self._db_url = db_url
        self._init_schema()

    def _get_conn(self) -> psycopg.Connection:
        """Get a new connection to the database."""
        return psycopg.connect(self._db_url, row_factory=dict_row)

    def _init_schema(self) -> None:
        """Create the searches and bot_config tables if they do not exist."""
        with self._get_conn() as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.execute(BOT_CONFIG_TABLE_SQL)
            conn.execute(USER_LOCATIONS_TABLE_SQL)
            conn.execute(LOCATION_CACHE_TABLE_SQL)
            conn.execute(LISTING_METADATA_TABLE_SQL)
            conn.execute("ALTER TABLE searches DROP COLUMN IF EXISTS city")
            conn.execute("ALTER TABLE searches ADD COLUMN IF NOT EXISTS location_name TEXT")
            conn.commit()
        logger.info("Database schema initialized.")

    def add_object(self, obj: SearchConfig) -> None:
        """Add a SearchConfig to the store."""
        terms_json = json.dumps(list(obj.terms))
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO searches (
                    id, terms, channel, city_code, location_name, target_price, days_listed, radius, context
                )
                VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    terms = EXCLUDED.terms,
                    channel = EXCLUDED.channel,
                    city_code = EXCLUDED.city_code,
                    location_name = EXCLUDED.location_name,
                    target_price = EXCLUDED.target_price,
                    days_listed = EXCLUDED.days_listed,
                    radius = EXCLUDED.radius,
                    context = EXCLUDED.context
                """,
                (
                    obj.id,
                    terms_json,
                    obj.channel,
                    obj.city_code,
                    obj.location_name,
                    obj.target_price,
                    obj.days_listed,
                    obj.radius,
                    obj.context,
                ),
            )
            conn.commit()
        logger.info(f"Search config '{obj.id}' saved to database.")

    def remove_object(self, obj: SearchConfig) -> None:
        """Remove a SearchConfig from the store by id."""
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM searches WHERE id = %s", (obj.id,))
            conn.commit()
            if cur.rowcount == 0:
                logger.warning(f"Search config '{obj.id}' not found in store.")

    def get_all_objects(self) -> set[SearchConfig]:
        """Retrieve all SearchConfig objects from the store."""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM searches")
            rows = cur.fetchall()
        return {_row_to_config(row) for row in rows}

    def get_config_by_id(self, search_id: str) -> SearchConfig | None:
        """Return SearchConfig for given id, or None."""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM searches WHERE id = %s", (search_id,))
            row = cur.fetchone()
        return _row_to_config(row) if row else None

    def record_listing_metadata(
        self,
        message_id: int,
        channel_id: int,
        search_id: str,
        thought_trace: str | None = None,
    ) -> None:
        """Store or update listing metadata for a Discord message."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO listing_metadata (message_id, channel_id, search_id, thought_trace)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (message_id) DO UPDATE SET
                    channel_id = EXCLUDED.channel_id,
                    search_id = EXCLUDED.search_id,
                    thought_trace = EXCLUDED.thought_trace
                """,
                (message_id, channel_id, search_id, thought_trace),
            )
            conn.commit()

    def get_listing_metadata(
        self, message_id: int
    ) -> dict[str, str | None] | None:
        """Return listing metadata for a message, or None if not found."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT search_id, thought_trace FROM listing_metadata WHERE message_id = %s",
                (message_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {"search_id": row["search_id"], "thought_trace": row.get("thought_trace")}

    def clear_store(self) -> None:
        """Clear all SearchConfig objects from the store."""
        with self._get_conn() as conn:
            conn.execute("TRUNCATE TABLE searches")
            conn.commit()
        logger.info("Store cleared.")

    def get_feed_channel_id(self) -> int | None:
        """Get the feed channel ID from bot_config, or None if not set."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT value FROM bot_config WHERE key = %s",
                ("feed_channel_id",),
            )
            row = cur.fetchone()
        if row and row.get("value"):
            try:
                return int(row["value"])
            except (ValueError, TypeError):
                return None
        return None

    def set_feed_channel_id(self, channel_id: int | None) -> None:
        """Set or clear the feed channel ID in bot_config."""
        with self._get_conn() as conn:
            if channel_id is None:
                conn.execute(
                    "DELETE FROM bot_config WHERE key = %s",
                    ("feed_channel_id",),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO bot_config (key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """,
                    ("feed_channel_id", str(channel_id)),
                )
            conn.commit()

    def get_user_location(self, user_id: int) -> UserLocation | None:
        """Get marketplace location settings for a user."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT user_id, city_code FROM user_locations WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return UserLocation(user_id=int(row["user_id"]), city_code=row["city_code"])

    def set_user_location(self, user_id: int, city_code: str) -> None:
        """Set or update a user's marketplace location settings."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO user_locations (user_id, city_code)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    city_code = EXCLUDED.city_code,
                    updated_at = NOW()
                """,
                (user_id, city_code),
            )
            conn.commit()

    def remove_user_location(self, user_id: int) -> bool:
        """Remove marketplace location settings for a user."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM user_locations WHERE user_id = %s",
                (user_id,),
            )
            conn.commit()
        return cur.rowcount > 0

    def get_location_name(self, city_code: str) -> str | None:
        """Get cached human-readable location name for a city code."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT location_name FROM location_cache WHERE city_code = %s",
                (city_code,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return row.get("location_name")

    def set_location_name(self, city_code: str, location_name: str) -> None:
        """Cache human-readable location name for a city code."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO location_cache (city_code, location_name)
                VALUES (%s, %s)
                ON CONFLICT (city_code) DO UPDATE SET
                    location_name = EXCLUDED.location_name
                """,
                (city_code, location_name),
            )
            conn.commit()
