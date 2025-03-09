import asyncio
import base64
import io
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from filelock import FileLock
from matplotlib.dates import DateFormatter
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from raspen_beere.dht22 import DHT22
from raspen_beere.file import get_sensor_file

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

    def get_last_measurement(self) -> list[dict[str, Any]] | None:
        json_file, lock_file = get_sensor_file()
        with FileLock(str(lock_file)):
            if json_file.is_file():
                with json_file.open("r") as f:
                    try:
                        data = json.load(f)
                        return data if data else None
                    except json.JSONDecodeError:
                        return None
        return None

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
        if user.id == self.admin_id or str(user.id) in self.whitelist:
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

        message = (
            "*Available Commands:*\n"
            "/sensor - Get sensor infos\n"
            "/graph - Get historical sensor infos"
        )
        await update.message.reply_markdown(message)

    async def sensor(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.check_authentication(update, context):
            return

        data = self.get_last_measurement()
        if data:
            last_measurement = data[-1]
            message = (
                "<b>Sensor Info</b>\n"
                f"Temperatur: {last_measurement['temperature']}°C\n"
                f"Luftfeuchtigkeit: {last_measurement['humidity']}%"
            )
        else:
            message = "⚠️ Noch keine Messdaten verfügbar."
        await update.message.reply_html(message)

    async def graph(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.check_authentication(update, context):
            return

        data = self.get_last_measurement()
        if data:
            times = [datetime.strptime(d["timestamp"], "%H:%M") for d in data]
            temps = [d["temperature"] for d in data]
            humidities = [d["humidity"] for d in data]

            # Create a plot with two y-axes (temperature and humidity)
            fig, ax1 = plt.subplots()

            # Plot temperature on primary y-axis
            ax1.plot(times, temps, "b-", label="Temperature")
            ax1.set_xlabel("Time")
            ax1.set_ylabel("Temperature (°C)", color="b")
            ax1.tick_params(axis="y", labelcolor="b")
            ax1.legend(loc="upper left")

            # Plot humidity on secondary y-axis
            ax2 = ax1.twinx()
            ax2.plot(times, humidities, "r-", label="Humidity")
            ax2.set_ylabel("Humidity (%)", color="r")
            ax2.tick_params(axis="y", labelcolor="r")
            ax2.legend(loc="upper right")

            ax1.xaxis.set_major_formatter(DateFormatter("%H:%M"))
            fig.autofmt_xdate()

            # Save the plot to a BytesIO buffer
            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            buf.seek(0)
            plt.close(fig)
            await update.message.reply_photo(buf, "Todays sensor data")
        else:
            message = "⚠️ Noch keine Messdaten verfügbar."
            await update.message.reply_html(message)

    async def pihole(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user.id != self.admin_id:
            return

        message = (
            f"URL: http://192.168.0.188/admin\n"
            f"Password: {os.environ['PIHOLE_PASSWORD']}"
        )
        await update.message.reply_markdown(message)

    async def history(self, update: Update, contect: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user.id != self.admin_id:
            return

        with open("/var/lib/pihole/pihole.log", "r", encoding="utf-8") as f:
            logs = f.readlines()
        filter = base64.b64decode("cG9ybg==").decode("utf-8")
        logs = [i for i in logs if filter in i.lower()]
        message = f"Found {len(logs)} entries:\n{logs}"
        await update.message.reply_markdown(message)

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
        self.app.add_handler(CommandHandler("graph", self.graph))
        self.app.add_handler(CommandHandler("pihole", self.pihole))
        self.app.add_handler(CommandHandler("history", self.history))
        self.app.add_handler(CallbackQueryHandler(self.button))
        # self.app.add_error_handler(self.error_handler)
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()
