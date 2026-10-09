"""Collect Solana token candidates and details from DexScreener."""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

try:
    from .config import settings, shadow_config
    from .db import get_recent_mints, init_db, save_token, save_filter_results, has_recent_shadow_alert, save_alert
    from .filters import evaluate_token, is_accepted
    from .security import secure_accepted_tokens
    from .narrative import evaluate_narratives
except ImportError:
    from config import settings, shadow_config
    from db import get_recent_mints, init_db, save_token, save_filter_results, has_recent_shadow_alert, save_alert
    from filters import evaluate_token, is_accepted
    from security import secure_accepted_tokens
    from narrative import evaluate_narratives

logger = logging.getLogger(__name__)


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def parse_pair(pair: dict[str, Any], now_ms: int | None = None) -> dict[str, Any] | None:
    """Convert a DexScreener pair to a database-ready token record."""
    if pair.get("chainId") != "solana":
        return None
    base = pair.get("baseToken") or {}
    mint = base.get("address")
    if not mint:
        return None
    txns = pair.get("txns") or {}
    volume = pair.get("volume") or {}
    liquidity = pair.get("liquidity") or {}
    info = pair.get("info") or {}
    created_at = _integer(pair.get("pairCreatedAt"))
    current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    websites = [item["url"] for item in info.get("websites", []) if item.get("url")]
    socials = [
        {key: str(item[key]) for key in ("platform", "handle") if item.get(key)}
        for item in info.get("socials", [])
    ]
    return {
        "mint": mint, "symbol": base.get("symbol"), "name": base.get("name"),
        "description": info.get("description"),
        "price_usd": _number(pair.get("priceUsd")), "liquidity_usd": _number(liquidity.get("usd")),
        "volume_m5": _number(volume.get("m5")), "volume_h1": _number(volume.get("h1")),
        "volume_h24": _number(volume.get("h24")),
        "buys_h1": _integer((txns.get("h1") or {}).get("buys")),
        "sells_h1": _integer((txns.get("h1") or {}).get("sells")),
        "buys_h24": _integer((txns.get("h24") or {}).get("buys")),
        "sells_h24": _integer((txns.get("h24") or {}).get("sells")),
        "pair_age_seconds": None if created_at is None else max(0, (current_ms - created_at) / 1000),
        "fdv": _number(pair.get("fdv")), "market_cap": _number(pair.get("marketCap")),
        "websites": websites, "socials": socials, "dex_id": pair.get("dexId"),
        "pair_address": pair.get("pairAddress"), "pair_url": pair.get("url"),
        "last_processed_at": datetime.now(timezone.utc).isoformat(),
    }


def _candidate_addresses(payload: Any) -> set[str]:
    items = payload if isinstance(payload, list) else payload.get("tokens", [])
    return {
        item["tokenAddress"] for item in items if isinstance(item, dict)
        and item.get("chainId") == "solana" and item.get("tokenAddress")
    }


def _candidate_metadata(payload: Any) -> dict[str, dict[str, Any]]:
    items = payload if isinstance(payload, list) else payload.get("tokens", [])
    return {
        item["tokenAddress"]: {
            "description": item.get("description"),
            "profile_url": item.get("url"),
            "profile_links": item.get("links", []),
        }
        for item in items if isinstance(item, dict)
        and item.get("chainId") == "solana" and item.get("tokenAddress")
    }


async def _get(client: httpx.AsyncClient, url: str) -> Any:
    for attempt in range(settings.max_retries + 1):
        try:
            response = await client.get(url)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                await asyncio.sleep(min(float(retry_after) if retry_after else 2**attempt, 60))
                continue
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            if attempt >= settings.max_retries:
                raise
            delay = min(2**attempt, 60)
            logger.warning("DexScreener request failed (%s), retrying in %ss", exc, delay)
            await asyncio.sleep(delay)
    raise RuntimeError("DexScreener request retries exhausted")


async def collect_filtered_tokens(client: httpx.AsyncClient | None = None) -> list[dict[str, Any]]:
    """Collect tokens and apply cheap filters, returning only cheap-filter winners."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    assert client is not None
    try:
        await init_db()
        addresses: set[str] = set()
        metadata: dict[str, dict[str, Any]] = {}
        for endpoint in (settings.dex_profiles_url, settings.dex_boosts_url):
            candidate_payload = await _get(client, endpoint)
            addresses.update(_candidate_addresses(candidate_payload))
            metadata.update(_candidate_metadata(candidate_payload))
            await asyncio.sleep(settings.request_pause_seconds)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.token_refresh_minutes)
        recent = await get_recent_mints(cutoff.isoformat())
        saved = 0
        accepted_tokens: list[dict[str, Any]] = []
        addresses_to_process = sorted(addresses - recent)[: settings.max_tokens_per_run]
        if len(addresses - recent) > len(addresses_to_process):
            logger.info("Limiting this run to %s tokens", settings.max_tokens_per_run)
        for address in addresses_to_process:
            try:
                payload = await _get(client, settings.dex_tokens_url.format(address=address))
                pairs = (payload.get("pairs") or []) if isinstance(payload, dict) else []
                tokens = [parse_pair(pair) for pair in pairs if isinstance(pair, dict)]
                tokens = [token for token in tokens if token is not None]
                if tokens:
                    token = max(tokens, key=lambda item: item.get("liquidity_usd") or 0)
                    profile = metadata.get(address, {})
                    if not token.get("description"):
                        token["description"] = profile.get("description")
                    if not token.get("websites") and profile.get("profile_url"):
                        token["websites"] = [profile["profile_url"]]
                    results = evaluate_token(token)
                    failed = [result[1] for result in results if not result[1][0]]
                    status = "accepted" if is_accepted(results) else "rejected"
                    reason = "; ".join(result[1] for result in failed) or "all filters passed"
                    await save_token(token, status=status, status_reason=reason)
                    await save_filter_results(token["mint"], results)
                    if status == "rejected" and shadow_config.get("enabled"):
                        cutoff_shadow = (datetime.now(timezone.utc) - timedelta(minutes=settings.token_refresh_minutes)).isoformat()
                        if not await has_recent_shadow_alert(token["mint"], cutoff_shadow):
                            await save_alert(token["mint"], 0, "shadow", datetime.now(timezone.utc).isoformat(), token.get("price_usd"), token.get("market_cap"), token.get("symbol"), token.get("name"), True)
                    saved += 1
                    if status == "accepted":
                        accepted_tokens.append(token)
            except Exception:
                logger.exception("Collection/filter failed for %s", address)
            await asyncio.sleep(settings.request_pause_seconds)
        logger.info("DexScreener stage: %s candidates, %s tokens saved, %s passed cheap filters", len(addresses), saved, len(accepted_tokens))
        return accepted_tokens
    finally:
        if own_client:
            await client.aclose()


async def collect_once(client: httpx.AsyncClient | None = None) -> int:
    """Run the legacy complete collection stage for callers that use collector directly."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    assert client is not None
    try:
        tokens = await collect_filtered_tokens(client)
        security_tokens = await secure_accepted_tokens(tokens)
        await evaluate_narratives(security_tokens)
        return len(security_tokens)
    finally:
        if own_client:
            await client.aclose()


async def run_forever() -> None:
    """Poll DexScreener until Ctrl+C."""
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        while True:
            try:
                await collect_once(client)
            except Exception:
                logger.exception("DexScreener collection cycle failed")
            await asyncio.sleep(settings.poll_interval_seconds)
