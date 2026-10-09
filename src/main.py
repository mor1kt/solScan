"""Single pipeline entry point: collect -> filter -> security -> narrative -> score -> alert."""

import argparse
import asyncio
import html
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .collector import collect_filtered_tokens
    from .config import outcomes_config, scoring_config, settings
    from .db import get_last_alert_score, get_security_result_map, get_stats, save_alert
    from .outcomes import outcomes_loop
    from .outcomes import process_due_outcomes
    from .report import build_report
    from .narrative import evaluate_narratives
    from .scoring import score_token_from_db
    from .security import secure_accepted_tokens
    from .telegram_bot import run_polling, send_alert
except ImportError:
    from collector import collect_filtered_tokens
    from config import outcomes_config, scoring_config, settings
    from db import get_last_alert_score, get_security_result_map, get_stats, save_alert
    from outcomes import outcomes_loop
    from outcomes import process_due_outcomes
    from report import build_report
    from narrative import evaluate_narratives
    from scoring import score_token_from_db
    from security import secure_accepted_tokens
    from telegram_bot import run_polling, send_alert

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    log_path = Path(settings.log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _value(security: dict[str, Any], name: str) -> Any:
    return (security.get(name) or {}).get("value")


def format_alert(token: dict[str, Any], result: Any) -> str:
    security = result.security
    narrative = result.narrative
    age_hours = (token.get("pair_age_seconds") or 0) / 3600
    flags = ", ".join(narrative.red_flags) if narrative and narrative.red_flags else "нет"
    summary = narrative.summary if narrative else "нарратив не оценён"
    mint = html.escape(str(token.get("mint", "")))
    mint_url = f"https://solscan.io/token/{mint}"
    dex_url = token.get("pair_url") or f"https://dexscreener.com/solana/{mint}"
    rug_url = f"https://rugcheck.xyz/tokens/{mint}"
    jupiter_url = f"https://jup.ag/swap/SOL-{mint}"
    components = " | ".join(f"{html.escape(name)}: {value:.1f}" for name, value in result.components.items())
    return (
        f"<b>{html.escape(str(token.get('symbol') or '?'))} — {html.escape(str(token.get('name') or 'Без названия'))}</b>\n"
        f"Mint: <code>{mint}</code>\n"
        f"Цена: ${token.get('price_usd') or 0:.8g} | Ликвидность: ${token.get('liquidity_usd') or 0:,.0f}\n"
        f"Объём 1ч: ${token.get('volume_h1') or 0:,.0f} | Market cap: ${token.get('market_cap') or 0:,.0f}\n"
        f"Возраст пары: {age_hours:.1f} ч | Топ-10: {_value(security, 'top10_holder_percent') or 'н/д'}%\n\n"
        f"<b>Скор: {result.total:.1f}/100</b>\n{components}\n\n"
        f"<b>Нарратив:</b> {html.escape(summary)}\n"
        f"<b>Красные флаги:</b> {html.escape(flags)}\n\n"
        f"<a href=\"{html.escape(str(dex_url), quote=True)}\">DexScreener</a> | "
        f"<a href=\"{html.escape(rug_url, quote=True)}\">RugCheck</a> | "
        f"<a href=\"{html.escape(mint_url, quote=True)}\">Solscan</a> | "
        f"<a href=\"{html.escape(jupiter_url, quote=True)}\">Jupiter</a>"
    )


async def should_send_alert(mint: str, score: float) -> bool:
    previous = await get_last_alert_score(mint)
    if previous is None:
        return True
    return score >= previous + float(scoring_config["repeat_score_delta"])


async def run_cycle(dry_run: bool = False) -> int:
    logger.info("Stage 1/6: collecting and applying cheap filters")
    cheap_tokens = await collect_filtered_tokens()
    logger.info("Stage 2/6: %s tokens passed cheap filters", len(cheap_tokens))

    logger.info("Stage 3/6: security checks")
    security_tokens = await secure_accepted_tokens(cheap_tokens)
    logger.info("Stage 4/6: %s tokens passed security", len(security_tokens))

    logger.info("Stage 5/6: narrative evaluation")
    await evaluate_narratives(security_tokens)
    logger.info("Stage 6/6: scoring and alerts")

    sent = 0
    threshold = float(scoring_config["alert_threshold"])
    repeat_delta = float(scoring_config["repeat_score_delta"])
    for token in security_tokens:
        try:
            result = await score_token_from_db(token)
            logger.info("Token %s score %.2f", token["mint"], result.total)
            if result.total < threshold:
                continue
            if not await should_send_alert(token["mint"], result.total):
                previous = await get_last_alert_score(token["mint"])
                logger.info("Skipping duplicate alert for %s (%.2f < %.2f)", token["mint"], result.total, (previous or 0) + repeat_delta)
                continue
            message = format_alert(token, result)
            if dry_run:
                print(message)
            else:
                await send_alert(message)
                await save_alert(
                    token["mint"], result.total, message, datetime.now(timezone.utc).isoformat(),
                    token.get("price_usd"), token.get("market_cap"), token.get("symbol"), token.get("name"), False,
                )
            sent += 1
        except Exception:
            logger.exception("Token pipeline failed for %s", token.get("mint"))
    return sent


async def run_forever(dry_run: bool = False) -> None:
    while True:
        try:
            await run_cycle(dry_run=dry_run)
        except Exception:
            logger.exception("Pipeline cycle failed")
        await asyncio.sleep(settings.poll_interval_seconds)


async def run_once(dry_run: bool = False) -> int:
    """Run one bounded GitHub Actions-compatible cycle and always return normally."""
    async def bounded_cycle() -> None:
        try:
            await run_cycle(dry_run=dry_run)
        finally:
            completed = await process_due_outcomes()
            if completed:
                logger.info("Run-once recorded %s previous alert outcomes", completed)

    try:
        await asyncio.wait_for(bounded_cycle(), timeout=settings.run_once_timeout_seconds)
    except asyncio.TimeoutError:
        logger.error("Run-once timed out after %s seconds", settings.run_once_timeout_seconds)
    except Exception:
        logger.exception("Run-once failed; returning success for scheduled execution")
    return 0


async def application(dry_run: bool = False) -> None:
    tasks = [run_forever(dry_run=dry_run)]
    if outcomes_config.get("enabled", True):
        tasks.append(outcomes_loop())
    if settings.telegram_bot_token:
        tasks.append(run_polling())
    await asyncio.gather(*tasks)


async def print_stats() -> None:
    total, rejected, reasons = await get_stats()
    print(f"Собрано токенов: {total}")
    print(f"Отсеяно: {rejected}")
    print("Причины отказа:")
    print("  нет данных" if not reasons else "")
    for reason, count in reasons:
        print(f"  {count}: {reason}")


async def _print_report(by_score: bool) -> None:
    print(await build_report(by_score=by_score))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=("stats", "report", "run-once"))
    parser.add_argument("--dry-run", action="store_true", help="print alerts instead of sending them")
    parser.add_argument("--by-score", action="store_true", help="group report by score ranges")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        configure_logging()
        if args.command == "stats":
            asyncio.run(print_stats())
        elif args.command == "report":
            asyncio.run(_print_report(args.by_score))
        elif args.command == "run-once":
            asyncio.run(run_once(dry_run=args.dry_run))
        else:
            asyncio.run(application(dry_run=args.dry_run))
    except KeyboardInterrupt:
        logger.info("Stopped by user")
