"""Telegram notifications."""

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

try:
    from .config import settings
except ImportError:
    from config import settings


async def run_polling() -> None:
    """Run the Telegram command handler for /stats."""
    if not settings.telegram_bot_token:
        return
    try:
        from .report import short_report
    except ImportError:
        from report import short_report

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()

    @dispatcher.message(Command("stats"))
    async def stats_handler(message) -> None:
        if settings.telegram_chat_id and str(message.chat.id) != str(settings.telegram_chat_id):
            return
        await message.answer(await short_report())

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


async def send_alert(text: str) -> None:
    """Send an HTML-formatted message to the configured Telegram chat."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(chat_id=settings.telegram_chat_id, text=text)
    finally:
        await bot.session.close()
