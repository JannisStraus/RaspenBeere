import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from raspen_beere.sensor import DHT22

# Set logging level for external libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self) -> None:
        data_dir = Path.cwd() / "data"
        data_dir.mkdir(exist_ok=True)
        self.dht22 = DHT22()
        self.whitelist_file = data_dir / "whitelist.json"
        self.blacklist_file = data_dir / "blacklist.json"
        self.admin_id = int(os.environ["TELEGRAM_ADMIN"])
        self.whitelist = self.load_json_users(self.whitelist_file)
        self.blacklist = self.load_json_users(self.blacklist_file)
        self.pending_requests: dict[int, dict[str, Any]] = {}
        self.lock = (
            asyncio.Lock()
        )  # Ensures safe modifications across concurrent requests

    def load_json_users(self, file_path: Path) -> dict[str, dict[str, Any]]:
        if not file_path.is_file():
            return {}

        with file_path.open("r") as f:
            data: dict[str, dict[str, Any]] = json.load(f)
        return data

    def save_json_users(self, file_path: Path, data: dict[str, dict[str, Any]]) -> None:
        with file_path.open("w") as f:
            json.dump(data, f, indent=2)

    async def check_authentication(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        user = update.effective_user

        # Check if the user is blacklisted
        if str(user.id) in self.blacklist:
            await update.message.reply_html(
                "🚫 Your access has been permanently denied."
            )
            return False

        # Check if the user is already whitelisted (or if they are the admin)
        if str(user.id) in self.whitelist:
            return True

        async with self.lock:
            if user.id in self.pending_requests:
                await update.message.reply_html(
                    "⚠️ Your access request is already pending."
                )
                return False

        await update.message.reply_html(
            "⚠️ You are not authenticated. Please wait while your request is reviewed."
        )

        user_info = {
            "id": user.id,
            "first_name": user.first_name or "Unknown",
            "last_name": user.last_name or "Unknown",
            "username": f"@{user.username}" if user.username else "Unknown",
            "language": user.language_code or "Unknown",
        }
        # Safely store the pending request
        async with self.lock:
            self.pending_requests[user.id] = user_info

        message = (
            "*Access Request*\n"
            f"Id: {user.id}\n"
            f"Username: {user_info['username']}\n"
            f"First Name: {user_info['first_name']}\n"
            f"Last Name: {user_info['last_name']}\n"
            f"Language: {user_info['language']}\n\n"
            "Grant access to this user?"
        )
        # Encode the target user's id in the callback data
        keyboard = [
            [
                InlineKeyboardButton("✅", callback_data=f"access_yes:{user.id}"),
                InlineKeyboardButton("🚫", callback_data=f"access_no:{user.id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.app.bot.send_message(
            chat_id=self.admin_id,
            text=message,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        return False

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.check_authentication(update, context):
            return

        message = "*Available Commands:*\n" "/sensor - Get Sensor infos"
        await update.message.reply_markdown(message)

    async def sensor(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.check_authentication(update, context):
            return

        temperature = await self.dht22.get_temperature()
        humidity = await self.dht22.get_humidity()
        message = (
            "<b>Sensor Info</b>\n"
            f"Temperatur: {temperature}°C\n"
            f"Luftfeuchtigkeit: {humidity}%"
        )
        await update.message.reply_html(message)

    async def button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        # Only allow the admin to interact with these buttons
        if update.effective_user.id != self.admin_id:
            return

        try:
            decision, target_id_str = query.data.split(":")
            target_id = int(target_id_str)
        except ValueError:
            logger.error("Invalid callback data format")
            return

        async with self.lock:
            user_info = self.pending_requests.pop(target_id, None)

        if not user_info:
            await query.edit_message_text(text="Request expired.")
            return

        if decision == "access_yes":
            async with self.lock:
                self.whitelist[str(target_id)] = user_info
                self.save_json_users(self.whitelist_file, self.whitelist)
            await query.edit_message_text(text="✅ Access granted.")
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="✅ Your access request has been approved.",
                )
            except Exception as e:
                logger.error(f"Failed to send message to user {target_id}: {e}")

        elif decision == "access_no":
            async with self.lock:
                self.blacklist[str(target_id)] = user_info
                self.save_json_users(self.blacklist_file, self.blacklist)
            await query.edit_message_text(text="🚫 Access denied.")
            try:
                await context.bot.send_message(
                    chat_id=target_id, text="🚫 Your access request has been denied."
                )
            except Exception as e:
                logger.error(f"Failed to send message to user {target_id}: {e}")

    def run(self) -> None:
        self.app = Application.builder().token(os.environ["TELEGRAM_TOKEN"]).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.start))
        self.app.add_handler(CommandHandler("sensor", self.sensor))
        self.app.add_handler(CallbackQueryHandler(self.button))
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()
