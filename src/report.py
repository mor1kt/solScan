"""Reports for sent alerts and their measured outcomes."""

import statistics
from collections import defaultdict
from typing import Any

import aiosqlite

try:
    from .db import _database_path, init_db
    from .config import outcomes_config
except ImportError:
    from db import _database_path, init_db
    from config import outcomes_config


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


async def _rows(include_shadow: bool = False) -> list[dict[str, Any]]:
    await init_db()
    async with aiosqlite.connect(_database_path()) as connection:
        connection.row_factory = aiosqlite.Row
        shadow_clause = "" if include_shadow else "AND a.is_shadow = 0"
        cursor = await connection.execute(
            f"""
            SELECT a.id, a.mint, a.symbol, a.name, a.score, a.price_usd, a.is_shadow,
                   o.horizon_minutes, o.return_pct, o.is_rug
            FROM alerts a LEFT JOIN alert_outcomes o ON o.alert_id = a.id
            WHERE 1=1 {shadow_clause}
            ORDER BY a.id
            """
        )
        return [dict(row) for row in await cursor.fetchall()]


async def build_report(by_score: bool = False) -> str:
    rows = await _rows()
    sent = len({row["id"] for row in rows})
    lines = [f"Алертов отправлено: {sent}"]
    horizons = [int(value) for value in outcomes_config["horizons_minutes"]]
    for horizon in horizons:
        values = [row["return_pct"] for row in rows if row["horizon_minutes"] == horizon and row["return_pct"] is not None]
        rugs = [row for row in rows if row["horizon_minutes"] == horizon]
        if not values:
            lines.append(f"{horizon}м: данных нет")
            continue
        losses = sum(value < -50 for value in values) / len(values) * 100
        rug_share = sum(row["is_rug"] for row in rugs) / len(rugs) * 100 if rugs else 0
        lines.append(f"{horizon}м: средняя {_fmt(statistics.mean(values))}, медиана {_fmt(statistics.median(values))}, -50%: {losses:.1f}%, раги: {rug_share:.1f}%")
    complete = {}
    final_horizon = max(horizons)
    for row in rows:
        if row["horizon_minutes"] == final_horizon and row["return_pct"] is not None:
            complete[row["id"]] = row
    if complete:
        best = max(complete.values(), key=lambda row: row["return_pct"])
        worst = min(complete.values(), key=lambda row: row["return_pct"])
        lines.append(f"Лучший: {best['symbol'] or best['mint']} {_fmt(best['return_pct'])}")
        lines.append(f"Худший: {worst['symbol'] or worst['mint']} {_fmt(worst['return_pct'])}")
    if by_score:
        lines.append("По диапазонам скора:")
        groups: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            if row["horizon_minutes"] == final_horizon and row["return_pct"] is not None and row["score"] is not None:
                score = float(row["score"])
                label = f"{int(score // 10) * 10}-{min(100, int(score // 10) * 10 + 9)}"
                groups[label].append(row["return_pct"])
        for label in sorted(groups):
            lines.append(f"  {label}: n={len(groups[label])}, средняя {_fmt(statistics.mean(groups[label]))}, медиана {_fmt(statistics.median(groups[label]))}")
    return "\n".join(lines)


async def short_report() -> str:
    rows = await _rows()
    sent = len({row["id"] for row in rows})
    final_horizon = max(int(value) for value in outcomes_config["horizons_minutes"])
    values = [row["return_pct"] for row in rows if row["horizon_minutes"] == final_horizon and row["return_pct"] is not None]
    return f"Алертов: {sent}\nДоходность через {final_horizon}м: {_fmt(statistics.mean(values)) if values else 'данных пока нет'}"
