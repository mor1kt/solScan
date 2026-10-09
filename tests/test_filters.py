import pytest

from src.config import filter_config
from src.filters import (
    max_fdv,
    max_pair_age_hours,
    max_sell_buy_ratio,
    min_buys_h1,
    min_liquidity_usd,
    min_market_cap,
    min_pair_age_minutes,
    min_volume_h1,
)


def test_min_liquidity_boundary() -> None:
    assert min_liquidity_usd({"liquidity_usd": filter_config["min_liquidity_usd"]})[0]
    assert not min_liquidity_usd({"liquidity_usd": filter_config["min_liquidity_usd"] - 1})[0]


def test_min_volume_boundary() -> None:
    assert min_volume_h1({"volume_h1": filter_config["min_volume_h1"]})[0]
    assert not min_volume_h1({"volume_h1": filter_config["min_volume_h1"] - 1})[0]


def test_min_age_boundary() -> None:
    boundary = filter_config["min_pair_age_minutes"] * 60
    assert min_pair_age_minutes({"pair_age_seconds": boundary})[0]
    assert not min_pair_age_minutes({"pair_age_seconds": boundary - 1})[0]


def test_max_age_boundary() -> None:
    boundary = filter_config["max_pair_age_hours"] * 3600
    assert max_pair_age_hours({"pair_age_seconds": boundary})[0]
    assert not max_pair_age_hours({"pair_age_seconds": boundary + 1})[0]


def test_min_buys_boundary() -> None:
    assert min_buys_h1({"buys_h1": filter_config["min_buys_h1"]})[0]
    assert not min_buys_h1({"buys_h1": filter_config["min_buys_h1"] - 1})[0]


def test_sell_buy_ratio_boundary() -> None:
    maximum = filter_config["max_sell_buy_ratio"]
    assert max_sell_buy_ratio({"buys_h1": 10, "sells_h1": 10 * maximum})[0]
    assert not max_sell_buy_ratio({"buys_h1": 10, "sells_h1": 10 * maximum + 1})[0]


def test_market_cap_boundary() -> None:
    assert min_market_cap({"market_cap": filter_config["min_market_cap"]})[0]
    assert not min_market_cap({"market_cap": filter_config["min_market_cap"] - 1})[0]


def test_fdv_boundary() -> None:
    assert max_fdv({"fdv": filter_config["max_fdv"]})[0]
    assert not max_fdv({"fdv": filter_config["max_fdv"] + 1})[0]


def test_filter_returns_three_values() -> None:
    result = min_liquidity_usd({"liquidity_usd": 0})
    assert len(result) == 3
    assert isinstance(result[0], bool)
