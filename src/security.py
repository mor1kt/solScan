"""Free, read-only security checks for tokens that passed cheap filters."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

try:
    from .config import filter_config, security_config, settings, shadow_config
    from .db import get_recent_security_statuses, save_security_results, update_token_status, save_alert, has_recent_shadow_alert
except ImportError:
    from config import filter_config, security_config, settings
    from db import get_recent_security_statuses, save_security_results, update_token_status, save_alert, has_recent_shadow_alert
    from config import shadow_config

logger = logging.getLogger(__name__)


def parse_rugcheck_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract stable security fields from the evolving RugCheck response."""
    risks = payload.get("risks") or []
    holders = payload.get("topHolders") or payload.get("top_holders") or []
    top10 = payload.get("top10HolderPercent", payload.get("top10", payload.get("top10Percent")))
    if top10 is None and isinstance(holders, list):
        eligible = [item for item in holders if not item.get("isPool") and not item.get("isLp")]
        top10 = sum(float(item.get("pct", item.get("percentage", 0)) or 0) for item in eligible[:10])
    markets = payload.get("markets") or []
    locked = payload.get("lockedLiquidity", payload.get("lpLocked", False))
    burned = payload.get("burnedLiquidity", payload.get("lpBurned", False))
    for market in markets:
        lp = market.get("lp") or market.get("liquidity") or {}
        locked = locked or bool(lp.get("lpLocked") or lp.get("locked") or (lp.get("lpLockedPct", 0) > 0))
        burned = burned or bool(lp.get("lpBurned") or lp.get("burned") or (lp.get("lpBurnedPct", 0) > 0))
    return {
        "risk_score": payload.get("score", payload.get("riskScore")),
        "risks": risks,
        "rugged": bool(payload.get("rugged")) or any("rug" in str(item).lower() for item in risks),
        "mint_authority": payload.get("mintAuthority"),
        "freeze_authority": payload.get("freezeAuthority"),
        "top10_holder_percent": top10,
        "locked_liquidity": bool(locked),
        "burned_liquidity": bool(burned),
        "creator": payload.get("creator") or payload.get("creatorInfo"),
    }


def parse_rpc_authorities(payload: dict[str, Any]) -> dict[str, Any]:
    value = ((payload.get("result") or {}).get("value") or {})
    parsed = (((value.get("data") or {}).get("parsed") or {}).get("info") or {})
    return {"mint_authority": parsed.get("mintAuthority"), "freeze_authority": parsed.get("freezeAuthority")}


def parse_jupiter_route(payload: dict[str, Any]) -> bool:
    return bool(payload.get("routePlan")) or bool(payload.get("outAmount"))


def _result(name: str, passed: bool, reason: str, value: Any) -> tuple[str, bool, str, Any]:
    return name, passed, reason, value


async def _request(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, method: str, url: str, **kwargs: Any) -> Any:
    async with semaphore:
        for attempt in range(settings.max_retries + 1):
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    delay = min(float(retry_after) if retry_after else 2**attempt, 60)
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                if attempt >= settings.max_retries:
                    raise
                await asyncio.sleep(min(2**attempt, 60))
                logger.warning("Security request failed (%s), retrying", exc)
    raise RuntimeError("security request retries exhausted")


async def check_token_security(token: dict[str, Any], client: httpx.AsyncClient, semaphore: asyncio.Semaphore) -> list[tuple[str, bool, str, Any]]:
    """Run RugCheck, RPC authority, and Jupiter sell-route checks for one token."""
    mint = token["mint"]
    rug_url = settings.rugcheck_summary_url.format(mint=mint)
    quote_params = {
        "inputMint": mint,
        "outputMint": security_config["jupiter_output_mint"],
        "amount": security_config["jupiter_sell_amount_raw"],
        "slippageBps": security_config["jupiter_slippage_bps"],
        "restrictIntermediateTokens": "true",
    }
    rpc_body = {
        "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
        "params": [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}],
    }
    rug_task = _request(client, semaphore, "GET", rug_url)
    rpc_task = _request(client, semaphore, "POST", settings.solana_rpc_url, json=rpc_body)
    quote_task = _request(client, semaphore, "GET", settings.jupiter_quote_url, params=quote_params)
    rug_payload, rpc_payload, quote_payload = await asyncio.gather(rug_task, rpc_task, quote_task, return_exceptions=True)
    results: list[tuple[str, bool, str, Any]] = []
    if isinstance(rug_payload, Exception):
        results.append(_result("rugcheck_report", False, f"RugCheck error: {rug_payload}", None))
        rug = {}
    else:
        rug = parse_rugcheck_summary(rug_payload)
        score = rug.get("risk_score")
        results.append(_result("rugcheck_score", score is not None and score <= security_config["max_risk_score"], "risk score within limit" if score is not None and score <= security_config["max_risk_score"] else "risk score unavailable or too high", score))
        results.append(_result("rugcheck_risks", True, "RugCheck risks collected", rug["risks"]))
        results.append(_result("rugcheck_authorities", True, "RugCheck authorities collected", {"mint": rug["mint_authority"], "freeze": rug["freeze_authority"]}))
        results.append(_result("rugged", not rug["rugged"], "not marked rugged" if not rug["rugged"] else "token marked rugged", rug["rugged"]))
        results.append(_result("top10_holder_percent", rug["top10_holder_percent"] is not None and rug["top10_holder_percent"] <= security_config["max_top10_holder_percent"], "top-10 concentration within limit" if rug["top10_holder_percent"] is not None and rug["top10_holder_percent"] <= security_config["max_top10_holder_percent"] else "top-10 concentration too high or unavailable", rug["top10_holder_percent"]))
        results.append(_result("locked_or_burned_lp", not security_config["require_locked_or_burned_lp"] or rug["locked_liquidity"] or rug["burned_liquidity"], "LP locked or burned" if rug["locked_liquidity"] or rug["burned_liquidity"] else "LP is not locked or burned", {"locked": rug["locked_liquidity"], "burned": rug["burned_liquidity"]}))
        results.append(_result("creator_info", rug["creator"] is not None, "creator information available" if rug["creator"] is not None else "creator information unavailable", rug["creator"]))
    if isinstance(rpc_payload, Exception):
        results.append(_result("revoked_authorities", False, f"Solana RPC error: {rpc_payload}", None))
    else:
        authorities = parse_rpc_authorities(rpc_payload)
        passed = not security_config["require_revoked_authorities"] or (authorities["mint_authority"] is None and authorities["freeze_authority"] is None)
        results.append(_result("revoked_authorities", passed, "mint and freeze authorities revoked" if passed else "mint or freeze authority is still active", authorities))
    if isinstance(quote_payload, Exception):
        results.append(_result("jupiter_sell_route", False, f"Jupiter quote error: {quote_payload}", None))
    else:
        routed = parse_jupiter_route(quote_payload)
        results.append(_result("jupiter_sell_route", routed, "sell route exists" if routed else "no sell route found", routed))
    return results


async def secure_token(token: dict[str, Any], client: httpx.AsyncClient, semaphore: asyncio.Semaphore) -> bool:
    results = await check_token_security(token, client, semaphore)
    checked_at = datetime.now(timezone.utc).isoformat()
    failed = [reason for _, passed, reason, _ in results if not passed]
    accepted = not failed
    if not accepted:
        logger.info("Security rejected %s: %s", token["mint"], "; ".join(failed))
    else:
        logger.info("Security accepted %s", token["mint"])
    await save_security_results(token["mint"], results, checked_at)
    await update_token_status(token["mint"], "accepted" if accepted else "rejected", "; ".join(failed) or "security checks passed")
    if not accepted and shadow_config.get("enabled"):
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=security_config["cache_minutes"])).isoformat()
        if not await has_recent_shadow_alert(token["mint"], cutoff):
            await save_alert(token["mint"], 0, "shadow", checked_at, token.get("price_usd"), token.get("market_cap"), token.get("symbol"), token.get("name"), True)
    return accepted


async def secure_accepted_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check accepted cheap-filter tokens, respecting cache and concurrency limits."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=security_config["cache_minutes"])
    recent_statuses = await get_recent_security_statuses(cutoff.isoformat())
    candidates = [token for token in tokens if token["mint"] not in recent_statuses]
    cached_accepted = [token for token in tokens if recent_statuses.get(token["mint"]) is True]
    cached_rejected = [token for token in tokens if recent_statuses.get(token["mint"]) is False]
    for token in cached_accepted:
        logger.info("Security cached accepted %s", token["mint"])
    for token in cached_rejected:
        logger.info("Security cached rejected %s", token["mint"])
    semaphore = asyncio.Semaphore(security_config["max_concurrent_requests"])
    async with httpx.AsyncClient(timeout=security_config["request_timeout_seconds"]) as client:
        results = await asyncio.gather(*(secure_token(token, client, semaphore) for token in candidates), return_exceptions=True)
    passed_tokens = list(cached_accepted)
    for token, result in zip(candidates, results):
        if isinstance(result, Exception):
            logger.error("Security check failed for %s: %s", token["mint"], result)
        elif result:
            passed_tokens.append(token)
    return passed_tokens
