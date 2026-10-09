"""Background tracking of alert performance at fixed time horizons."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

try:
    from .config import outcomes_config, settings
    from .db import get_due_outcome_alerts, save_alert_outcome
except ImportError:
    from config import outcomes_config, settings
    from db import get_due_outcome_alerts, save_alert_outcome

logger = logging.getLogger(__name__)


def calculate_return(initial_price: float | None, current_price: float | None) -> float | None:
    if initial_price is None or current_price is None or initial_price <= 0:
        return None
    return round((current_price / initial_price - 1) * 100, 4)


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


async def fetch_snapshot(client: httpx.AsyncClient, mint: str) -> dict[str, float | None]:
    response = await client.get(settings.dex_tokens_url.format(address=mint))
    response.raise_for_status()
    payload = response.json()
    pairs = [pair for pair in (payload.get("pairs") or []) if pair.get("chainId") == "solana"]
    pairs = [pair for pair in pairs if (pair.get("baseToken") or {}).get("address") == mint]
    if not pairs:
        return {"price_usd": None, "market_cap": None, "liquidity_usd": 0.0}
    pair = max(pairs, key=lambda item: _number((item.get("liquidity") or {}).get("usd")) or 0)
    return {
        "price_usd": _number(pair.get("priceUsd")),
        "market_cap": _number(pair.get("marketCap")),
        "liquidity_usd": _number((pair.get("liquidity") or {}).get("usd")),
    }


async def process_due_outcomes() -> int:
    now = datetime.now(timezone.utc).isoformat()
    horizons = [int(value) for value in outcomes_config["horizons_minutes"]]
    due = await get_due_outcome_alerts(now, horizons, int(outcomes_config.get("max_outcomes_per_run", 20)))
    if not due:
        return 0
    completed = 0
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        for item in due:
            try:
                snapshot = await fetch_snapshot(client, item["mint"])
                await save_alert_outcome(
                    item["id"], item["horizon_minutes"], now,
                    snapshot["price_usd"], snapshot["market_cap"], snapshot["liquidity_usd"],
                    calculate_return(item["price_usd"], snapshot["price_usd"]),
                    snapshot["liquidity_usd"] == 0,
                )
                completed += 1
            except Exception:
                logger.exception("Outcome check failed for alert %s", item["id"])
    return completed


async def outcomes_loop() -> None:
    while True:
        try:
            count = await process_due_outcomes()
            if count:
                logger.info("Recorded %s alert outcomes", count)
        except Exception:
            logger.exception("Outcome worker failed")
        await asyncio.sleep(int(outcomes_config["check_interval_seconds"]))
