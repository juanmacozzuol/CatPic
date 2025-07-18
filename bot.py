import os
import json
import logging
import asyncio

from datetime import datetime
from telegram import InputFile, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

TOKEN = os.getenv("BOT_TOKEN")
PHOTOS_FOLDER = "photos"
USERS_FILE = "users.json"
SENT_FILE = "sent.json"

scheduler = BackgroundScheduler()
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

# --- Envío asíncrono real ---
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
            photo_path = os.path.join(PHOTOS_FOLDER, photo)
            with open(photo_path, "rb") as f:
                await app.bot.send_photo(chat_id=user_id, photo=InputFile(f))
            user_sent.append(photo)
            sent[str(user_id)] = user_sent
            save_json(SENT_FILE, sent)
        except Exception as e:
            print(f"Error sending to {user_id}: {e}")

# --- Versión sincrónica para APScheduler ---
def send_photo_to_user_sync(app, user_id, loop):
    asyncio.run_coroutine_threadsafe(send_photo_to_user(app, user_id), loop)

# --- Programar tareas ---
def schedule_user_job(app, user_id, time_str, loop):
    hour, minute = map(int, time_str.split(":"))
    user_tz = ZoneInfo("America/Argentina/Buenos_Aires")
    trigger = CronTrigger(hour=hour, minute=minute, timezone=user_tz)

    scheduler.add_job(send_photo_to_user_sync, trigger, args=[app, user_id, loop], id=str(user_id), replace_existing=True)

# --- Comandos ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        users[user_id] = {"time": "10:00"}
        save_json(USERS_FILE, users)

    loop = asyncio.get_event_loop()
    schedule_user_job(context.application, user_id, users[user_id]["time"], loop)

    for ext in ("jpg", "jpeg", "png", "webp"):
        start_path = os.path.join(PHOTOS_FOLDER, f"start.{ext}")
        if os.path.exists(start_path):
            try:
                with open(start_path, "rb") as f:
                    await update.message.reply_photo(photo=InputFile(f), caption="¡Bienvenido al Cat Pic of the Day!")
                return
            except Exception as e:
                await update.message.reply_text(f"Error al enviar la imagen de inicio: {e}")
    await update.message.reply_text("No se encontró imagen de inicio.")

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Uso: /time HH:MM (formato 24h)")
        return

    time_str = context.args[0]
    try:
        datetime.strptime(time_str, "%H:%M")
        users[user_id] = {"time": time_str}
        save_json(USERS_FILE, users)
        loop = asyncio.get_event_loop()
        schedule_user_job(context.application, user_id, time_str, loop)
        await update.message.reply_text(f"¡Hora actualizada! Recibirás fotos a las {time_str}.")
    except ValueError:
        await update.message.reply_text("Formato inválido. Usa HH:MM en formato 24 horas.")

# --- Arranque principal ---
def run_bot():
    app = Application.builder().token(TOKEN).build()
    main_loop = asyncio.get_event_loop()

    scheduler.start()

    for uid, data in users.items():
        schedule_user_job(app, uid, data["time"], main_loop)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("time", set_time))

    app.run_polling()

if __name__ == "__main__":
    run_bot()
