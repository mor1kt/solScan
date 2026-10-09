import json
from pathlib import Path

import httpx
import pytest

from src.security import check_token_security, parse_jupiter_route, parse_rugcheck_summary, parse_rpc_authorities


ROOT = Path(__file__).parents[1]


def load_fixture(name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))


def test_parse_rugcheck_summary() -> None:
    result = parse_rugcheck_summary(load_fixture("rugcheck_summary.json"))
    assert result["risk_score"] == 120
    assert result["top10_holder_percent"] == pytest.approx(20)
    assert result["locked_liquidity"] is True
    assert result["creator"]["address"] == "Creator111"


def test_parse_rpc_and_jupiter() -> None:
    assert parse_rpc_authorities(load_fixture("solana_rpc_account.json")) == {
        "mint_authority": None,
        "freeze_authority": None,
    }
    assert parse_jupiter_route(load_fixture("jupiter_quote.json")) is True
    assert parse_jupiter_route({"error": "Could not find any route"}) is False


@pytest.mark.asyncio
async def test_security_checks_use_mocked_responses() -> None:
    rug = load_fixture("rugcheck_summary.json")
    rpc = load_fixture("solana_rpc_account.json")
    quote = load_fixture("jupiter_quote.json")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json=rpc)
        if "rugcheck" in str(request.url):
            return httpx.Response(200, json=rug)
        return httpx.Response(200, json=quote)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await check_token_security(
            {"mint": "Mint111111111111111111111111111111111111111"},
            client,
            __import__("asyncio").Semaphore(3),
        )
    assert all(passed for _, passed, _, _ in results)
