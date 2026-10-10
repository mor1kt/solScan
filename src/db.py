"""SQLite helpers for collected token data."""

import json
from pathlib import Path
from typing import Any

import aiosqlite

try:
    from .config import settings
except ImportError:
    from config import settings


def _database_path() -> Path:
    database = Path(settings.database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    return database


async def init_db() -> None:
    """Create the database directory and initialize the database."""
    async with aiosqlite.connect(_database_path()) as connection:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL, mint TEXT, score REAL, price_usd REAL, market_cap REAL,
                symbol TEXT, name TEXT, is_shadow INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        alert_columns = {row[1] for row in await (await connection.execute("PRAGMA table_info(alerts)")).fetchall()}
        for column, definition in (
            ("mint", "TEXT"), ("score", "REAL"), ("price_usd", "REAL"),
            ("market_cap", "REAL"), ("symbol", "TEXT"), ("name", "TEXT"),
            ("is_shadow", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if column not in alert_columns:
                await connection.execute(f"ALTER TABLE alerts ADD COLUMN {column} {definition}")
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                mint TEXT PRIMARY KEY, symbol TEXT, name TEXT, description TEXT, price_usd REAL,
                liquidity_usd REAL, volume_m5 REAL, volume_h1 REAL, volume_h24 REAL,
                buys_h1 INTEGER, sells_h1 INTEGER, buys_h24 INTEGER, sells_h24 INTEGER,
                pair_age_seconds REAL, fdv REAL, market_cap REAL,
                websites_json TEXT NOT NULL DEFAULT '[]', socials_json TEXT NOT NULL DEFAULT '[]',
                dex_id TEXT, pair_address TEXT, pair_url TEXT, last_processed_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'collected', status_reason TEXT
            )
            """
        )
        columns = {row[1] for row in await (await connection.execute("PRAGMA table_info(tokens)")).fetchall()}
        for column, definition in (("description", "TEXT"), ("status", "TEXT NOT NULL DEFAULT 'collected'"), ("status_reason", "TEXT")):
            if column not in columns:
                await connection.execute(f"ALTER TABLE tokens ADD COLUMN {column} {definition}")
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS filter_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT, mint TEXT NOT NULL,
                filter_name TEXT NOT NULL, passed INTEGER NOT NULL,
                reason TEXT NOT NULL, value TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS security_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT, mint TEXT NOT NULL,
                check_name TEXT NOT NULL, passed INTEGER NOT NULL,
                reason TEXT NOT NULL, value TEXT, checked_at TEXT NOT NULL
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS narrative_results (
                mint TEXT PRIMARY KEY, status TEXT NOT NULL, result_json TEXT,
                reason TEXT, created_at TEXT NOT NULL
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS narrative_usage (
                day TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_outcomes (
                alert_id INTEGER NOT NULL, horizon_minutes INTEGER NOT NULL,
                checked_at TEXT NOT NULL, price_usd REAL, market_cap REAL,
                liquidity_usd REAL, return_pct REAL, is_rug INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (alert_id, horizon_minutes)
            )
            """
        )
        await connection.commit()


async def get_recent_mints(cutoff_iso: str) -> set[str]:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        cursor = await connection.execute("SELECT mint FROM tokens WHERE last_processed_at >= ?", (cutoff_iso,))
        rows = await cursor.fetchall()
    return {row[0] for row in rows}


async def save_token(token: dict[str, Any], status: str = "collected", status_reason: str | None = None) -> None:
    await init_db()
    fields = (
        token["mint"], token.get("symbol"), token.get("name"), token.get("description"), token.get("price_usd"),
        token.get("liquidity_usd"), token.get("volume_m5"), token.get("volume_h1"), token.get("volume_h24"),
        token.get("buys_h1"), token.get("sells_h1"), token.get("buys_h24"), token.get("sells_h24"),
        token.get("pair_age_seconds"), token.get("fdv"), token.get("market_cap"),
        json.dumps(token.get("websites", []), ensure_ascii=False),
        json.dumps(token.get("socials", []), ensure_ascii=False), token.get("dex_id"),
        token.get("pair_address"), token.get("pair_url"), token["last_processed_at"],
        status, status_reason,
    )
    async with aiosqlite.connect(_database_path()) as connection:
        await connection.execute(
            """
            INSERT INTO tokens (mint, symbol, name, description, price_usd, liquidity_usd, volume_m5, volume_h1, volume_h24,
                buys_h1, sells_h1, buys_h24, sells_h24, pair_age_seconds, fdv, market_cap, websites_json,
                socials_json, dex_id, pair_address, pair_url, last_processed_at, status, status_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mint) DO UPDATE SET
                symbol=excluded.symbol, name=excluded.name, description=excluded.description, price_usd=excluded.price_usd,
                liquidity_usd=excluded.liquidity_usd, volume_m5=excluded.volume_m5,
                volume_h1=excluded.volume_h1, volume_h24=excluded.volume_h24,
                buys_h1=excluded.buys_h1, sells_h1=excluded.sells_h1,
                buys_h24=excluded.buys_h24, sells_h24=excluded.sells_h24,
                pair_age_seconds=excluded.pair_age_seconds, fdv=excluded.fdv,
                market_cap=excluded.market_cap, websites_json=excluded.websites_json,
                socials_json=excluded.socials_json, dex_id=excluded.dex_id,
                pair_address=excluded.pair_address, pair_url=excluded.pair_url,
                last_processed_at=excluded.last_processed_at, status=excluded.status,
                status_reason=excluded.status_reason
            """, fields,
        )
        await connection.commit()


async def save_filter_results(mint: str, results: list[tuple[str, tuple[bool, str, Any]]]) -> None:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        await connection.execute("DELETE FROM filter_results WHERE mint = ?", (mint,))
        await connection.executemany(
            "INSERT INTO filter_results (mint, filter_name, passed, reason, value) VALUES (?, ?, ?, ?, ?)",
            [(mint, name, int(result[0]), result[1], str(result[2])) for name, result in results],
        )
        await connection.commit()


async def get_stats() -> tuple[int, int, list[tuple[str, int]]]:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        total = (await (await connection.execute("SELECT COUNT(*) FROM tokens")).fetchone())[0]
        rejected = (await (await connection.execute("SELECT COUNT(*) FROM tokens WHERE status = 'rejected'")).fetchone())[0]
        cursor = await connection.execute(
            "SELECT status_reason, COUNT(*) FROM tokens WHERE status = 'rejected' GROUP BY status_reason ORDER BY COUNT(*) DESC"
        )
        reasons = await cursor.fetchall()
    return total, rejected, reasons


async def get_recent_security_mints(cutoff_iso: str) -> set[str]:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        cursor = await connection.execute(
            "SELECT DISTINCT mint FROM security_results WHERE checked_at >= ?", (cutoff_iso,)
        )
        rows = await cursor.fetchall()
    return {row[0] for row in rows}


async def get_recent_security_statuses(cutoff_iso: str) -> dict[str, bool]:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        cursor = await connection.execute(
            "SELECT mint, MIN(passed) FROM security_results WHERE checked_at >= ? GROUP BY mint",
            (cutoff_iso,),
        )
        rows = await cursor.fetchall()
    return {row[0]: bool(row[1]) for row in rows}


async def update_token_status(mint: str, status: str, reason: str) -> None:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        await connection.execute(
            "UPDATE tokens SET status = ?, status_reason = ? WHERE mint = ?",
            (status, reason, mint),
        )
        await connection.commit()


async def save_security_results(
    mint: str, results: list[tuple[str, bool, str, Any]], checked_at: str
) -> None:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        await connection.execute("DELETE FROM security_results WHERE mint = ?", (mint,))
        await connection.executemany(
            """
            INSERT INTO security_results (mint, check_name, passed, reason, value, checked_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(mint, name, int(passed), reason, str(value), checked_at) for name, passed, reason, value in results],
        )
        await connection.commit()


async def get_similar_tokens(mint: str, name: str | None, symbol: str | None, limit: int = 10) -> list[dict[str, Any]]:
    await init_db()
    terms = [term.strip().lower() for term in (name, symbol) if term and term.strip()]
    if not terms:
        return []
    clauses = " OR ".join("LOWER(name) LIKE ? OR LOWER(symbol) LIKE ?" for _ in terms)
    params: list[Any] = []
    for term in terms:
        pattern = f"%{term}%"
        params.extend((pattern, pattern))
    params.extend((mint, limit))
    async with aiosqlite.connect(_database_path()) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            f"SELECT mint, name, symbol, description FROM tokens WHERE mint != ? AND ({clauses}) ORDER BY last_processed_at DESC LIMIT ?",
            params,
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_recent_narrative_mints(cutoff_iso: str) -> set[str]:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        cursor = await connection.execute("SELECT mint FROM narrative_results WHERE created_at >= ?", (cutoff_iso,))
        rows = await cursor.fetchall()
    return {row[0] for row in rows}


async def reserve_narrative_call(daily_limit: int, day: str) -> bool:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        await connection.execute("BEGIN IMMEDIATE")
        row = await (await connection.execute("SELECT calls FROM narrative_usage WHERE day = ?", (day,))).fetchone()
        calls = row[0] if row else 0
        if calls >= daily_limit:
            await connection.rollback()
            return False
        await connection.execute(
            "INSERT INTO narrative_usage (day, calls) VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET calls = calls + 1",
            (day,),
        )
        await connection.commit()
    return True


async def save_narrative_result(mint: str, status: str, result_json: str | None, reason: str | None, created_at: str) -> None:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        await connection.execute(
            """
            INSERT INTO narrative_results (mint, status, result_json, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(mint) DO UPDATE SET status=excluded.status, result_json=excluded.result_json,
                reason=excluded.reason, created_at=excluded.created_at
            """,
            (mint, status, result_json, reason, created_at),
        )
        await connection.commit()


async def get_security_result_map(mint: str) -> dict[str, Any]:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        cursor = await connection.execute("SELECT check_name, passed, value, reason FROM security_results WHERE mint = ?", (mint,))
        rows = await cursor.fetchall()
    return {row[0]: {"passed": bool(row[1]), "value": row[2], "reason": row[3]} for row in rows}


async def get_narrative_result(mint: str) -> dict[str, Any] | None:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        row = await (await connection.execute("SELECT status, result_json, reason FROM narrative_results WHERE mint = ?", (mint,))).fetchone()
    if not row:
        return None
    return {"status": row[0], "result_json": row[1], "reason": row[2]}


async def get_last_alert_score(mint: str) -> float | None:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        row = await (await connection.execute("SELECT score FROM alerts WHERE mint = ? AND is_shadow = 0 ORDER BY id DESC LIMIT 1", (mint,))).fetchone()
    return None if not row or row[0] is None else float(row[0])


async def save_alert(mint: str, score: float, text: str, created_at: str, price_usd: float | None = None, market_cap: float | None = None, symbol: str | None = None, name: str | None = None, is_shadow: bool = False) -> int:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        cursor = await connection.execute(
            "INSERT INTO alerts (text, mint, score, price_usd, market_cap, symbol, name, is_shadow, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (text, mint, score, price_usd, market_cap, symbol, name, int(is_shadow), created_at),
        )
        await connection.commit()
        return cursor.lastrowid


async def has_recent_shadow_alert(mint: str, cutoff_iso: str) -> bool:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        row = await (await connection.execute(
            "SELECT 1 FROM alerts WHERE mint = ? AND is_shadow = 1 AND created_at >= ? LIMIT 1",
            (mint, cutoff_iso),
        )).fetchone()
    return row is not None


async def get_due_outcome_alerts(now_iso: str, horizons: list[int], limit: int = 20) -> list[dict[str, Any]]:
    await init_db()
    placeholders = ",".join("?" for _ in horizons)
    async with aiosqlite.connect(_database_path()) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            f"""
            SELECT a.id, a.mint, a.price_usd, a.market_cap, a.created_at, a.is_shadow,
                   h.horizon_minutes
            FROM alerts a CROSS JOIN (SELECT value AS horizon_minutes FROM json_each(?)) h
            LEFT JOIN alert_outcomes o ON o.alert_id = a.id AND o.horizon_minutes = h.horizon_minutes
            WHERE o.alert_id IS NULL AND datetime(a.created_at, '+' || h.horizon_minutes || ' minutes') <= datetime(?)
            ORDER BY a.id LIMIT ?
            """,
            (json.dumps(horizons), now_iso, limit),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def save_alert_outcome(alert_id: int, horizon_minutes: int, checked_at: str, price_usd: float | None, market_cap: float | None, liquidity_usd: float | None, return_pct: float | None, is_rug: bool) -> None:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        await connection.execute(
            """
            INSERT OR REPLACE INTO alert_outcomes
            (alert_id, horizon_minutes, checked_at, price_usd, market_cap, liquidity_usd, return_pct, is_rug)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (alert_id, horizon_minutes, checked_at, price_usd, market_cap, liquidity_usd, return_pct, int(is_rug)),
        )
        await connection.commit()
