import pytest

import src.main as app
from src.scoring import (
    ScoreResult,
    liquidity_volume_score,
    narrative_score,
    score_token,
    trading_dynamics_score,
)
from src.narrative import NarrativeAssessment


def test_scoring_components_and_weighted_total() -> None:
    token = {
        "liquidity_usd": 10000,
        "volume_h1": 5000,
        "buys_h1": 90,
        "sells_h1": 10,
    }
    security = {
        name: {"passed": True, "value": "", "reason": ""}
        for name in ("rugcheck_score", "rugged", "locked_or_burned_lp", "revoked_authorities", "jupiter_sell_route")
    }
    narrative = NarrativeAssessment(
        theme="meme", originality=8, meme_potential=8, trend_relevance=8,
        is_copy=False, red_flags=[], summary="Good narrative",
    )
    result = score_token(token, security, narrative)
    assert isinstance(result, ScoreResult)
    assert liquidity_volume_score(token) == 100
    assert trading_dynamics_score(token) == 90
    assert narrative_score(narrative) == 80
    assert 0 <= result.total <= 100


def test_narrative_copy_is_penalized() -> None:
    original = NarrativeAssessment(theme="m", originality=8, meme_potential=8, trend_relevance=8, is_copy=False, red_flags=[], summary="x")
    copied = original.model_copy(update={"is_copy": True})
    assert narrative_score(copied) < narrative_score(original)


@pytest.mark.asyncio
async def test_alert_repeat_requires_score_increase(monkeypatch: pytest.MonkeyPatch) -> None:
    async def previous_score(mint: str) -> float:
        return 70

    monkeypatch.setattr(app, "get_last_alert_score", previous_score)
    assert await app.should_send_alert("M", 74) is False
    assert await app.should_send_alert("M", 75) is True
