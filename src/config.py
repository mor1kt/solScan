"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import yaml

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_YAML_PATH = Path(os.getenv("CONFIG_YAML_PATH", PROJECT_ROOT / "config.yaml"))
runtime_config: dict[str, Any] = {}


def load_filter_config() -> dict[str, Any]:
    if not CONFIG_YAML_PATH.exists():
        raise FileNotFoundError(f"Filter configuration not found: {CONFIG_YAML_PATH}")
    with CONFIG_YAML_PATH.open(encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data.get("filters", {})


def load_security_config() -> dict[str, Any]:
    if not CONFIG_YAML_PATH.exists():
        raise FileNotFoundError(f"Security configuration not found: {CONFIG_YAML_PATH}")
    with CONFIG_YAML_PATH.open(encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data.get("security", {})


def load_narrative_config() -> dict[str, Any]:
    if not CONFIG_YAML_PATH.exists():
        raise FileNotFoundError(f"Narrative configuration not found: {CONFIG_YAML_PATH}")
    with CONFIG_YAML_PATH.open(encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data.get("narrative", {})


def load_scoring_config() -> dict[str, Any]:
    if not CONFIG_YAML_PATH.exists():
        raise FileNotFoundError(f"Scoring configuration not found: {CONFIG_YAML_PATH}")
    with CONFIG_YAML_PATH.open(encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data.get("scoring", {})


def load_outcomes_config() -> dict[str, Any]:
    if not CONFIG_YAML_PATH.exists():
        raise FileNotFoundError(f"Outcomes configuration not found: {CONFIG_YAML_PATH}")
    with CONFIG_YAML_PATH.open(encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data.get("outcomes", {})


def load_shadow_config() -> dict[str, Any]:
    if not CONFIG_YAML_PATH.exists():
        raise FileNotFoundError(f"Shadow configuration not found: {CONFIG_YAML_PATH}")
    with CONFIG_YAML_PATH.open(encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data.get("shadow", {})


def load_runtime_config() -> dict[str, Any]:
    if not CONFIG_YAML_PATH.exists():
        raise FileNotFoundError(f"Runtime configuration not found: {CONFIG_YAML_PATH}")
    with CONFIG_YAML_PATH.open(encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data.get("runtime", {})


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    database_path: str = "data/solana_scanner.db"
    log_path: str = "logs/app.log"
    dex_base_url: str = "https://api.dexscreener.com"
    dex_profiles_url: str = "https://api.dexscreener.com/token-profiles/latest/v1"
    dex_boosts_url: str = "https://api.dexscreener.com/token-boosts/latest/v1"
    dex_tokens_url: str = "https://api.dexscreener.com/latest/dex/tokens/{address}"
    poll_interval_seconds: int = 60
    token_refresh_minutes: int = 15
    request_pause_seconds: float = 0.25
    request_timeout_seconds: float = 15.0
    max_retries: int = 4
    max_tokens_per_run: int = 25
    max_outcomes_per_run: int = 20
    run_once_timeout_seconds: int = 220
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    rugcheck_summary_url: str = "https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
    jupiter_quote_url: str = "https://lite-api.jup.ag/swap/v1/quote"
    gemini_api_key: str = ""
    groq_api_key: str = ""


runtime_config = load_runtime_config()

settings = Settings(
    telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
    telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    database_path=os.getenv("DB_PATH", os.getenv("DATABASE_PATH", "data/solana_scanner.db")),
    log_path=os.getenv("LOG_PATH", "logs/app.log"),
    dex_base_url=os.getenv("DEX_BASE_URL", "https://api.dexscreener.com"),
    dex_profiles_url=os.getenv("DEX_PROFILES_URL", "https://api.dexscreener.com/token-profiles/latest/v1"),
    dex_boosts_url=os.getenv("DEX_BOOSTS_URL", "https://api.dexscreener.com/token-boosts/latest/v1"),
    dex_tokens_url=os.getenv("DEX_TOKENS_URL", "https://api.dexscreener.com/latest/dex/tokens/{address}"),
    poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
    token_refresh_minutes=int(os.getenv("TOKEN_REFRESH_MINUTES", "15")),
    request_pause_seconds=float(os.getenv("REQUEST_PAUSE_SECONDS", "0.25")),
    request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15")),
    max_retries=int(os.getenv("MAX_RETRIES", "4")),
    max_tokens_per_run=int(os.getenv("MAX_TOKENS_PER_RUN", str(runtime_config.get("max_tokens_per_run", 25)))),
    max_outcomes_per_run=int(os.getenv("MAX_OUTCOMES_PER_RUN", str(runtime_config.get("max_outcomes_per_run", 20)))),
    run_once_timeout_seconds=int(os.getenv("RUN_ONCE_TIMEOUT_SECONDS", str(runtime_config.get("run_once_timeout_seconds", 220)))),
    solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
    rugcheck_summary_url=os.getenv(
        "RUGCHECK_SUMMARY_URL", "https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
    ),
    jupiter_quote_url=os.getenv("JUPITER_QUOTE_URL", "https://lite-api.jup.ag/swap/v1/quote"),
    gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
    groq_api_key=os.getenv("GROQ_API_KEY", ""),
)

filter_config = load_filter_config()
security_config = load_security_config()
narrative_config = load_narrative_config()
scoring_config = load_scoring_config()
outcomes_config = load_outcomes_config()
shadow_config = load_shadow_config()
