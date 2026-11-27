"""SQLite TTL cache for claim checks. The connection stays open so :memory: survives."""
import json
import sqlite3
import time

from agl.core.claim_cache import make_key, ttl_for


class ClaimStore:
    """One table, one connection. Expired rows are misses and stay until overwritten."""

    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS claim_cache (
                cache_key TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def get_many(self, claims, context=""):
        """({original claim: result dict}, [uncached claims]). Expired rows are misses."""
        found, uncached = {}, []
        now = time.time()
        for claim in claims:
            parsed = self._live(make_key(claim, context), now)
            if parsed is None:
                uncached.append(claim)
            else:
                found[claim] = parsed
        return found, uncached

    def set_many(self, results, context=""):
        """Store each dict's claim. expires_at is now plus the TTL for that status."""
        now = time.time()
        for result in results:
            self._conn.execute(
                """
                INSERT INTO claim_cache (cache_key, result_json, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    result_json = excluded.result_json,
                    expires_at = excluded.expires_at
                """,
                (
                    make_key(result["claim"], context),
                    json.dumps(result),
                    now + ttl_for(result["status"]),
                ),
            )
        self._conn.commit()

    def _live(self, key, now):
        row = self._conn.execute(
            "SELECT result_json, expires_at FROM claim_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if row is None or row[1] <= now:
            return None
        try:
            parsed = json.loads(row[0])
        except ValueError:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed
