"""Deterministic 0-100 scoring for tokens that passed all required checks."""

import json
from dataclasses import dataclass
from typing import Any

try:
    from .config import filter_config, scoring_config, security_config
    from .db import get_narrative_result, get_security_result_map
    from .narrative import NarrativeAssessment
except ImportError:
    from config import filter_config, scoring_config, security_config
    from db import get_narrative_result, get_security_result_map
    from narrative import NarrativeAssessment


@dataclass(frozen=True)
class ScoreResult:
    total: float
    components: dict[str, float]
    narrative: NarrativeAssessment | None
    security: dict[str, Any]


def _bounded_ratio(value: Any, minimum: float) -> float:
    if value is None or minimum <= 0:
        return 0.0
    return max(0.0, min(1.0, float(value) / minimum))


def _as_number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def liquidity_volume_score(token: dict[str, Any]) -> float:
    liquidity = _bounded_ratio(token.get("liquidity_usd"), float(filter_config["min_liquidity_usd"]))
    volume = _bounded_ratio(token.get("volume_h1"), float(filter_config["min_volume_h1"]))
    return round((liquidity + volume) * 50, 2)


def holder_structure_score(security: dict[str, Any]) -> float:
    value = _as_number((security.get("top10_holder_percent") or {}).get("value"))
    if value is None:
        return 0.0
    maximum = float(security_config["max_top10_holder_percent"])
    return round(max(0.0, min(100.0, (1 - value / maximum) * 100)), 2)


def security_score(security: dict[str, Any]) -> float:
    names = ("rugcheck_score", "rugged", "locked_or_burned_lp", "revoked_authorities", "jupiter_sell_route")
    if not all(name in security for name in names):
        return 0.0
    return round(sum(100.0 if security[name]["passed"] else 0.0 for name in names) / len(names), 2)


def trading_dynamics_score(token: dict[str, Any]) -> float:
    buys = _as_number(token.get("buys_h1")) or 0
    sells = _as_number(token.get("sells_h1")) or 0
    total = buys + sells
    return round(buys / total * 100, 2) if total else 0.0


def narrative_score(narrative: NarrativeAssessment | None) -> float:
    if narrative is None:
        return 0.0
    value = (narrative.originality + narrative.meme_potential + narrative.trend_relevance) / 3 * 10
    if narrative.is_copy:
        value *= 0.5
    value -= min(30, len(narrative.red_flags) * 10)
    return round(max(0.0, min(100.0, value)), 2)


def score_token(token: dict[str, Any], security: dict[str, Any], narrative: NarrativeAssessment | None) -> ScoreResult:
    components = {
        "liquidity_volume": liquidity_volume_score(token),
        "holder_structure": holder_structure_score(security),
        "security": security_score(security),
        "trading_dynamics": trading_dynamics_score(token),
        "narrative": narrative_score(narrative),
    }
    weights = scoring_config["weights"]
    total_weight = sum(float(weights[name]) for name in components)
    total = sum(components[name] * float(weights[name]) for name in components) / total_weight if total_weight else 0.0
    return ScoreResult(round(max(0.0, min(100.0, total)), 2), components, narrative, security)


async def score_token_from_db(token: dict[str, Any]) -> ScoreResult:
    security = await get_security_result_map(token["mint"])
    stored = await get_narrative_result(token["mint"])
    narrative = None
    if stored and stored["status"] == "evaluated" and stored["result_json"]:
        try:
            narrative = NarrativeAssessment.model_validate_json(stored["result_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            narrative = None
    return score_token(token, security, narrative)
