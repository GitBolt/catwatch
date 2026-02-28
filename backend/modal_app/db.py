"""
Async DB helpers using asyncpg.
"""

import os
import asyncpg

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.environ["DATABASE_URL"],
            min_size=2,
            max_size=10,
        )
    return _pool


async def validate_api_key(key: str):
    """Validate an API key. Returns {api_key_id, user_id} or None."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT ak.id AS api_key_id, ak."userId" AS user_id
        FROM "ApiKey" ak
        WHERE ak.key = $1
        """,
        key,
    )
    if row:
        # Update lastUsed timestamp
        await pool.execute(
            'UPDATE "ApiKey" SET "lastUsed" = NOW() WHERE id = $1',
            row["api_key_id"],
        )
        return {"api_key_id": row["api_key_id"], "user_id": row["user_id"]}
    return None


async def create_session(
    session_id: str,
    api_key_id: str,
    user_id: str,
    mode: str = "general",
    unit_serial: str = None,
    model: str = None,
    fleet_tag: str = None,
):
    """Insert a new inspection session."""
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO "Session" (id, "apiKeyId", "userId", mode, status, "createdAt",
                               "unitSerial", model, "fleetTag")
        VALUES ($1, $2, $3, $4, 'active', NOW(), $5, $6, $7)
        """,
        session_id, api_key_id, user_id, mode, unit_serial, model, fleet_tag,
    )


async def save_finding(session_id: str, zone: str, rating: str, description: str):
    """Insert a finding for a session."""
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO "Finding" (id, "sessionId", zone, rating, description, "createdAt")
        VALUES (gen_random_uuid(), $1, $2, $3, $4, NOW())
        """,
        session_id, zone, rating, description,
    )


async def save_report(session_id: str, data: str):
    """Insert or update the report for a session."""
    import json
    pool = await get_pool()
    json_data = data if isinstance(data, str) else json.dumps(data)
    await pool.execute(
        """
        INSERT INTO "Report" (id, "sessionId", data, "createdAt")
        VALUES (gen_random_uuid(), $1, $2::jsonb, NOW())
        ON CONFLICT ("sessionId") DO UPDATE SET data = $2::jsonb
        """,
        session_id, json_data,
    )


async def end_session(session_id: str, zones_seen: int = 0, coverage_pct: float = 0.0):
    """Mark a session as completed."""
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE "Session"
        SET status = 'completed', "endedAt" = NOW(),
            "zonesSeen" = $2, "coveragePct" = $3
        WHERE id = $1
        """,
        session_id, zones_seen, coverage_pct,
    )
