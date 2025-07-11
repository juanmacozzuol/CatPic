import os
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

from telegram import InputFile, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

TOKEN = os.getenv("BOT_TOKEN")
PHOTOS_FOLDER = "photos"
USERS_FILE = "users.json"
SENT_FILE = "sent.json"

scheduler = AsyncIOScheduler()
logging.basicConfig(level=logging.INFO)

def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return default

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f)

users = load_json(USERS_FILE, {})
sent = load_json(SENT_FILE, {})

def get_photo_list():
    return sorted(f for f in os.listdir(PHOTOS_FOLDER) if not f.lower().startswith("start"))

async def send_photo_to_user(app, user_id):
    logging.info(f"Enviando foto al usuario {user_id} en {datetime.now()}")
    photo_list = get_photo_list()
    user_sent = sent.get(str(user_id), [])

    available = [p for p in photo_list if p not in user_sent]

    if not available:
        user_sent = []
        available = photo_list

    if available:
        photo = available[0]
        try:
            await app.bot.send_photo(chat_id=user_id, photo=InputFile(os.path.join(PHOTOS_FOLDER, photo)))
            user_sent.append(photo)
            sent[str(user_id)] = user_sent
            save_json(SENT_FILE, sent)
        except Exception as e:
            logging.error(f"Error sending to {user_id}: {e}")

def schedule_user_job(app, user_id, time_str):
    hour, minute = map(int, time_str.split(":"))
    user_tz = ZoneInfo("America/Argentina/Buenos_Aires")
    trigger = CronTrigger(hour=hour, minute=minute, timezone=user_tz)
    scheduler.add_job(send_photo_to_user, trigger, args=[app, user_id], id=str(user_id), replace_existing=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        users[user_id] = {"time": "10:00"}
        save_json(USERS_FILE, users)

    schedule_user_job(context.application, user_id, users[user_id]["time"])

    found = False
    for ext in ("jpg", "jpeg", "png", "webp"):
        start_path = os.path.join(PHOTOS_FOLDER, f"start.{ext}")
        if os.path.exists(start_path):
            try:
                with open(start_path, "rb") as f:
                    await update.message.reply_photo(photo=InputFile(f), caption="¡Bienvenido al Cat Pic of the Day!")
                found = True
                break
            except Exception as e:
                await update.message.reply_text(f"Failed to send start image: {e}")
                logging.error(f"Error sending start image: {e}")

    if not found:
        await update.message.reply_text("No start image found.")

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Usage: /time HH:MM (24h format)")
        return

    time_str = context.args[0]
    try:
        datetime.strptime(time_str, "%H:%M")
        users[user_id] = {"time": time_str}
        save_json(USERS_FILE, users)
        schedule_user_job(context.application, user_id, time_str)
        await update.message.reply_text(f"Time updated! You'll now receive photos at {time_str}.")
    except ValueError:
        await update.message.reply_text("Invalid time format. Use HH:MM in 24-hour format.")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("time", set_time))

    # Programar jobs para usuarios existentes
    for uid, data in users.items():
        schedule_user_job(app, uid, data["time"])

    scheduler.start()

    # run_polling maneja el loop de asyncio internamente, no usar asyncio.run()
    app.run_polling()

if __name__ == "__main__":
    main()