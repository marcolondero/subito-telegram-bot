import os
import sqlite3
import requests
from bs4 import BeautifulSoup
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler
import threading
import time
from datetime import datetime, time as dtime

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

def get_user(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT chat_id, cities, price_min, price_max, sqm_min FROM users WHERE chat_id = ?", (chat_id,))
    user = c.fetchone()
    conn.close()
    return user

def save_user(chat_id, cities, price_min, price_max, sqm_min):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO users (chat_id, cities, price_min, price_max, sqm_min)
                 VALUES (?, ?, ?, ?, ?)''',
              (chat_id, cities, price_min, price_max, sqm_min))
    conn.commit()
    conn.close()

def scrape_listings(city, price_min, price_max):
    url = f"https://www.subito.it/ville-singole-e-a-schiera/{city}/"
    resp = requests.get(url)
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    listings = []

    ads = soup.select('.items__item')
    for ad in ads:
        title_tag = ad.select_one('.item-description-title-link')
        if not title_tag:
            continue
        title = title_tag.text.strip()
        relative_url = title_tag.get('href')
        full_url = 'https://www.subito.it' + relative_url

        price_tag = ad.select_one('.items__price')
        price_text = price_tag.text.strip() if price_tag else "0"
        price_num = int(''.join(filter(str.isdigit, price_text)) or "0")

        if not (price_min <= price_num <= price_max):
            continue

        city_tag = ad.select_one('.item-location')
        city_name = city_tag.text.strip() if city_tag else city

        img_tag = ad.select_one('img')
        photo_url = img_tag.get('src') if img_tag else None

        listings.append({
            'title': title,
            'url': full_url,
            'price': price_text,
            'city': city_name,
            'photo_url': photo_url
        })

    return listings

def send_listings(chat_id):
    user = get_user(chat_id)
    if not user:
        bot.send_message(chat_id=chat_id, text="Non hai filtri impostati, usa /start.")
        return

    _, cities, price_min, price_max, sqm_min = user
    city_list = [c.strip() for c in cities.split(',')]
    found_any = False

    for city in city_list:
        listings = scrape_listings(city, price_min, price_max)
        for listing in listings:
            caption = (
                f"{listing['title']}\n"
                f"Città: {listing['city']}\n"
                f"Prezzo: {listing['price']}\n"
                f"Link: {listing['url']}"
            )
            if listing['photo_url']:
                bot.send_photo(chat_id=chat_id, photo=listing['photo_url'], caption=caption)
            else:
                bot.send_message(chat_id=chat_id, text=caption)
            found_any = True

    if not found_any:
        bot.send_message(chat_id=chat_id, text="Nessun annuncio trovato con i tuoi filtri.")

def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    default_cities = "pagnacco,martignacco,colloredo-di-monte-albano,moruzzo,reana-del-rojale,tricesimo,tavagnacco"
    default_price_min = 100000
    default_price_max = 340000
    default_sqm_min = 120

    save_user(chat_id, default_cities, default_price_min, default_price_max, default_sqm_min)
    update.message.reply_text(
        f"Benvenuto! Filtri impostati:\n"
        f"Città: {default_cities}\n"
        f"Prezzo: {default_price_min}-{default_price_max} €\n"
        f"Mq min: {default_sqm_min}\n"
        f"Usa /cercaora per cercare ora.\n"
        f"Usa /setcities, /setprice, /setsqm per cambiare i filtri."
    )

def cercaora(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    update.message.reply_text("Cerco annunci ora...")
    send_listings(chat_id)

# Command to set cities
def setcities(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if not context.args:
        update.message.reply_text("Uso: /setcities città separate da virgola\n(es. pagnacco,martignacco)")
        return
    cities = ','.join([arg.strip() for arg in context.args])
    user = get_user(chat_id)
    if user:
        _, _, price_min, price_max, sqm_min = user
    else:
        price_min, price_max, sqm_min = 100000, 340000, 120
    save_user(chat_id, cities, price_min, price_max, sqm_min)
    update.message.reply_text(f"Città aggiornate: {cities}")

# Command to set price range
def setprice(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if len(context.args) != 2:
        update.message.reply_text("Uso: /setprice prezzo_min prezzo_max\n(es. 100000 340000)")
        return
    try:
        price_min = int(context.args[0])
        price_max = int(context.args[1])
    except ValueError:
        update.message.reply_text("Inserisci numeri validi per prezzo_min e prezzo_max")
        return
    if price_min > price_max:
        update.message.reply_text("prezzo_min non può essere maggiore di prezzo_max")
        return
    user = get_user(chat_id)
    if user:
        _, cities, _, _, sqm_min = user
    else:
        cities = "pagnacco,martignacco,colloredo-di-monte-albano,moruzzo,reana-del-rojale,tricesimo,tavagnacco"
        sqm_min = 120
    save_user(chat_id, cities, price_min, price_max, sqm_min)
    update.message.reply_text(f"Prezzo aggiornato: {price_min} - {price_max} €")

# Command to set sqm min
def setsqm(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if len(context.args) != 1:
        update.message.reply_text("Uso: /setsqm metri_quadrati_min\n(es. 120)")
        return
    try:
        sqm_min = int(context.args[0])
    except ValueError:
        update.message.reply_text("Inserisci un numero valido per metri quadrati minimi")
        return
    user = get_user(chat_id)
    if user:
        _, cities, price_min, price_max, _ = user
    else:
        cities = "pagnacco,martignacco,colloredo-di-monte-albano,moruzzo,reana-del-rojale,tricesimo,tavagnacco"
        price_min = 100000
        price_max = 340000
    save_user(chat_id, cities, price_min, price_max, sqm_min)
    update.message.reply_text(f"Metri quadrati minimi aggiornati a: {sqm_min}")

# Scheduler function to run cercaora 4 times per day
def schedule_searches(updater: Updater):
    def job():
        while True:
            now = datetime.now()
            # Define times in 24h format when to run
            run_times = [dtime(8, 0), dtime(12, 0), dtime(16, 0), dtime(20, 0)]

            for target_time in run_times:
                # Wait until next target time
                while datetime.now().time() < target_time:
                    time.sleep(10)
                print(f"Running scheduled search at {target_time}")
                users = get_users()
                for user in users:
                    chat_id = user[0]
                    send_listings(chat_id)
                # Sleep a minute to avoid running multiple times in same minute
                time.sleep(60)

    thread = threading.Thread(target=job, daemon=True)
    thread.start()

def main():
    init_db()
    updater = Updater(token=TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('cercaora', cercaora))
    dispatcher.add_handler(CommandHandler('setcities', setcities))
    dispatcher.add_handler(CommandHandler('setprice', setprice))
    dispatcher.add_handler(CommandHandler('setsqm', setsqm))

    schedule_searches(updater)

    updater.start_polling()
    print("Bot attivo e scheduler avviato...")
    updater.idle()

if __name__ == "__main__":
    main()
