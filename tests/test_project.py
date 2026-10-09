from pathlib import Path
import json

import pytest

from src.collector import parse_pair


def test_required_files_exist() -> None:
    root = Path(__file__).parents[1]
    for path in (
        "src/config.py",
        "src/db.py",
        "src/telegram_bot.py",
        "src/main.py",
        ".env.example",
        ".gitignore",
        "requirements.txt",
        "README.md",
        "src/collector.py",
        "tests/fixtures/dexscreener_pair.json",
    ):
        assert (root / path).exists()


def test_parse_solana_pair() -> None:
    root = Path(__file__).parents[1]
    pair = json.loads((root / "tests/fixtures/dexscreener_pair.json").read_text())
    token = parse_pair(pair, now_ms=1760003600000)
    assert token is not None
    assert token["symbol"] == "MEME"
    assert token["price_usd"] == pytest.approx(0.00123)
    assert token["volume_h1"] == 1200
    assert token["buys_h24"] == 120
    assert token["pair_age_seconds"] == pytest.approx(3600)
    assert token["websites"] == ["https://example.com"]


def test_parse_ignores_non_solana_pair() -> None:
    assert parse_pair({"chainId": "ethereum"}) is None
