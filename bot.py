import os
import sqlite3
import requests
import threading
import time
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TOKEN:
    print("Error: TELEGRAM_TOKEN environment variable missing.")
    exit(1)

bot = Bot(token=TOKEN)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 chat_id INTEGER PRIMARY KEY,
                 cities TEXT,
                 price_min INTEGER,
                 price_max INTEGER,
                 sqm_min INTEGER)''')
    conn.commit()
    conn.close()

def get_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT chat_id, cities, price_min, price_max, sqm_min FROM users")
    rows = c.fetchall()
    conn.close()
    return rows

def save_user(chat_id, cities, price_min, price_max, sqm_min):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO users (chat_id, cities, price_min, price_max, sqm_min)
                 VALUES (?, ?, ?, ?, ?)''',
              (chat_id, cities, price_min, price_max, sqm_min))
    conn.commit()
    conn.close()

def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    default_cities = "pagnacco,martignacco,colloredo-di-monte-albano,moruzzo,reana-del-rojale,tricesimo,tavagnacco"
    default_price_min = 100000
    default_price_max = 340000
    default_sqm_min = 120

    save_user(chat_id, default_cities, default_price_min, default_price_max, default_sqm_min)
    update.message.reply_text(f"Benvenuto! Filtri impostati:\nCittà: {default_cities}\nPrezzo: {default_price_min}-{default_price_max} €\nMq min: {default_sqm_min}\nUsa /cercaora per cercare ora.")

def cercaora(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    users = get_users()
    user = next((u for u in users if u[0] == chat_id), None)
    if not user:
        update.message.reply_text("Non hai filtri impostati, usa /start.")
        return
    cities, price_min, price_max, sqm_min = user[1], user[2], user[3], user[4]
    update.message.reply_text(f"Cerco annunci per città: {cities}...")

    # Qui andrebbe la chiamata a funzione di scraping (da implementare)
    # Per esempio, simuliamo un annuncio:
    update.message.reply_text(f"Nuovo annuncio!\nCittà: {cities.split(',')[0]}\nPrezzo: {price_min + 5000} €\nMq: {sqm_min + 10}\nLink: https://www.subito.it/annuncio-esempio")

def main():
    init_db()
    updater = Updater(token=TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('cercaora', cercaora))

    updater.start_polling()
    print("Bot attivo...")
    updater.idle()

if __name__ == "__main__":
    main()
