"""
Telegram Bot Service - Handle Telegram bot lifecycle and message routing.

Architecture:
- Uses python-telegram-bot library (async)
- Receives messages via webhook (set by connect endpoint)
- Routes messages to Hyper AI service for processing
- Sends AI responses back to Telegram chat
"""
import asyncio
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import BotConfig, HyperAiConversation
from services.bot_service import get_decrypted_bot_token, update_bot_status

logger = logging.getLogger(__name__)

# Global bot application instance
_telegram_app = None


def _get_telegram_bot():
    """Lazy import telegram to avoid startup errors if not installed."""
    try:
        from telegram import Bot
        return Bot
    except ImportError:
        logger.warning("python-telegram-bot not installed")
        return None


async def validate_telegram_token(token: str) -> dict:
    """Validate a Telegram bot token by calling getMe."""
    Bot = _get_telegram_bot()
    if not Bot:
        return {"valid": False, "error": "python-telegram-bot not installed"}

    try:
        bot = Bot(token=token)
        me = await bot.get_me()
        return {
            "valid": True,
            "username": me.username,
            "bot_id": str(me.id),
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


async def setup_telegram_webhook(token: str, webhook_url: str) -> dict:
    """Set webhook URL for the Telegram bot."""
    Bot = _get_telegram_bot()
    if not Bot:
        return {"success": False, "error": "python-telegram-bot not installed"}

    try:
        bot = Bot(token=token)
        await bot.set_webhook(url=webhook_url)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def remove_telegram_webhook(token: str) -> dict:
    """Remove webhook for the Telegram bot."""
    Bot = _get_telegram_bot()
    if not Bot:
        return {"success": False, "error": "python-telegram-bot not installed"}

    try:
        bot = Bot(token=token)
        await bot.delete_webhook()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _strip_markdown(text: str) -> str:
    """Strip Markdown formatting to produce clean plain text."""
    text = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).strip('`').strip(), text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    return text


async def _send_single_message(bot, chat_id: int, text: str):
    """Send a single message with Markdown fallback to plain text."""
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    except Exception:
        plain = _strip_markdown(text)
        await bot.send_message(chat_id=chat_id, text=plain)


async def send_telegram_message(token: str, chat_id: int, text: str) -> bool:
    """Send a message to a Telegram chat."""
    Bot = _get_telegram_bot()
    if not Bot:
        return False

    try:
        bot = Bot(token=token)
        if len(text) <= 4096:
            await _send_single_message(bot, chat_id, text)
        else:
            chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
            for chunk in chunks:
                await _send_single_message(bot, chat_id, chunk)
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


async def restore_telegram_webhook():
    """Restore webhook on startup using the last successful webhook URL from DB."""
    db = SessionLocal()
    try:
        config = db.query(BotConfig).filter(
            BotConfig.platform == "telegram",
            BotConfig.status == "connected"
        ).first()
        if not config or not config.bot_token_encrypted or not config.webhook_url:
            return

        from services.bot_service import get_decrypted_bot_token
        token = get_decrypted_bot_token(db, "telegram")
        if not token:
            return

        result = await setup_telegram_webhook(token, config.webhook_url)
        if result["success"]:
            print(f"[startup] Telegram webhook restored: {config.webhook_url}", flush=True)
        else:
            print(f"[startup] Telegram webhook restore failed: {result.get('error')}", flush=True)
            from services.bot_service import update_bot_status
            update_bot_status(db, "telegram", "error", result.get("error"))
    except Exception as e:
        print(f"[startup] Telegram webhook restore error: {e}", flush=True)
    finally:
        db.close()


# ============================================================================
# Telegram Bot Adapter (implements BotAdapter interface)
# ============================================================================
class TelegramAdapter:
    """Telegram bot adapter implementing the unified BotAdapter interface."""

    def __init__(self):
        self._token: Optional[str] = None
        self._ready: bool = False

    @property
    def platform(self) -> str:
        return "telegram"

    def is_ready(self) -> bool:
        return self._ready and self._token is not None

    async def send_message(self, chat_id: str, content: str) -> bool:
        """Send message to Telegram chat."""
        if not self._token:
            return False
        return await send_telegram_message(self._token, int(chat_id), content)

    async def start(self, token: str) -> bool:
        """Start the adapter with the given token."""
        self._token = token
        self._ready = True
        logger.info(f"[TelegramAdapter] Started")
        return True

    async def stop(self) -> None:
        """Stop the adapter."""
        self._ready = False
        self._token = None
        logger.info(f"[TelegramAdapter] Stopped")


# Global adapter instance
_telegram_adapter: Optional[TelegramAdapter] = None


def get_telegram_adapter() -> TelegramAdapter:
    """Get or create the global Telegram adapter instance."""
    global _telegram_adapter
    if _telegram_adapter is None:
        _telegram_adapter = TelegramAdapter()
    return _telegram_adapter
