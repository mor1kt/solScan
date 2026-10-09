"""Cheap token filters that use only already-collected DexScreener data."""

from typing import Any

try:
    from .config import filter_config
except ImportError:
    from config import filter_config

FilterResult = tuple[bool, str, Any]


def _result(name: str, passed: bool, value: Any) -> FilterResult:
    return passed, (f"{name}: passed" if passed else f"{name}: rejected"), value


def min_liquidity_usd(token: dict[str, Any]) -> FilterResult:
    value = token.get("liquidity_usd")
    return _result("min_liquidity_usd", value is not None and value >= filter_config["min_liquidity_usd"], value)


def min_volume_h1(token: dict[str, Any]) -> FilterResult:
    value = token.get("volume_h1")
    return _result("min_volume_h1", value is not None and value >= filter_config["min_volume_h1"], value)


def min_pair_age_minutes(token: dict[str, Any]) -> FilterResult:
    value = None if token.get("pair_age_seconds") is None else token["pair_age_seconds"] / 60
    return _result("min_pair_age_minutes", value is not None and value >= filter_config["min_pair_age_minutes"], value)


def max_pair_age_hours(token: dict[str, Any]) -> FilterResult:
    value = None if token.get("pair_age_seconds") is None else token["pair_age_seconds"] / 3600
    return _result("max_pair_age_hours", value is not None and value <= filter_config["max_pair_age_hours"], value)


def min_buys_h1(token: dict[str, Any]) -> FilterResult:
    value = token.get("buys_h1")
    return _result("min_buys_h1", value is not None and value >= filter_config["min_buys_h1"], value)


def max_sell_buy_ratio(token: dict[str, Any]) -> FilterResult:
    buys = token.get("buys_h1") or 0
    sells = token.get("sells_h1") or 0
    value = sells / buys if buys else (0 if sells == 0 else float("inf"))
    return _result("max_sell_buy_ratio", value <= filter_config["max_sell_buy_ratio"], value)


def min_market_cap(token: dict[str, Any]) -> FilterResult:
    value = token.get("market_cap")
    return _result("min_market_cap", value is not None and value >= filter_config["min_market_cap"], value)


def max_fdv(token: dict[str, Any]) -> FilterResult:
    value = token.get("fdv")
    return _result("max_fdv", value is not None and value <= filter_config["max_fdv"], value)


FILTERS = (
    min_liquidity_usd, min_volume_h1, min_pair_age_minutes, max_pair_age_hours,
    min_buys_h1, max_sell_buy_ratio, min_market_cap, max_fdv,
)


def evaluate_token(token: dict[str, Any]) -> list[tuple[str, FilterResult]]:
    return [(filter_function.__name__, filter_function(token)) for filter_function in FILTERS]


def is_accepted(results: list[tuple[str, FilterResult]]) -> bool:
    return all(result[0] for _, result in results)
