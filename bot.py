import os
import sqlite3
import requests
from bs4 import BeautifulSoup
from telegram import Bot, Update, BotCommand
from telegram.ext import Updater, CommandHandler, CallbackContext
from datetime import datetime
import threading
import time

BASE_URL = "https://www.subito.it"
REGION = "annunci-friuli-venezia-giulia"
CATEGORY = "ville-singole-e-a-schiera"
PROVINCE = "udine"

DB_PATH = 'database.db'
TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TOKEN:
    print("Error: TELEGRAM_TOKEN env var missing.")
    exit(1)

bot = Bot(token=TOKEN)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            cities TEXT,
            price_min INTEGER,
            price_max INTEGER,
            sqm_min INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sent_listings (
            chat_id INTEGER,
            listing_id TEXT,
            PRIMARY KEY (chat_id, listing_id)
        )
    ''')
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
    c.execute('''
        INSERT OR REPLACE INTO users (chat_id, cities, price_min, price_max, sqm_min)
        VALUES (?, ?, ?, ?, ?)
    ''', (chat_id, cities, price_min, price_max, sqm_min))
    conn.commit()
    conn.close()

def listing_already_sent(chat_id, listing_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT 1 FROM sent_listings WHERE chat_id=? AND listing_id=?', (chat_id, listing_id))
    found = c.fetchone() is not None
    conn.close()
    return found

def mark_listing_sent(chat_id, listing_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO sent_listings (chat_id, listing_id) VALUES (?, ?)', (chat_id, listing_id))
    conn.commit()
    conn.close()

def build_search_url(city, price_min, price_max, sqm_min):
    return (f"{BASE_URL}/{REGION}/vendita/{CATEGORY}/{PROVINCE}/{city}/"
            f"?ps={price_min}&pe={price_max}&szs={sqm_min}")

def scrape_listings(city, price_min, price_max, sqm_min):
    url = build_search_url(city, price_min, price_max, sqm_min)
    print(f"Scraping URL: {url}")
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch listings for {city} with status {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    listings = []

    cards = soup.find_all("article", class_="items__item")
    print(f"Found {len(cards)} listings in {city}")

    for card in cards:
        a_tag = card.find("a", href=True)
        if not a_tag:
            continue
        link = BASE_URL + a_tag['href']
        listing_id = link.rstrip('/').split('-')[-1].replace('.htm', '')

        title = a_tag.get_text(strip=True)

        price_tag = card.find("span", class_="items__price")
        price = None
        if price_tag:
            price_str = price_tag.get_text(strip=True).replace('.', '').replace('€', '').strip()
            try:
                price = int(price_str)
            except Exception as e:
                print(f"Price parse error: {e}")

        sqm = None
        params_div = card.find("ul", class_="items__params")
        if params_div:
            for li in params_div.find_all("li"):
                text = li.get_text()
                if 'm²' in text:
                    try:
                        sqm = int(''.join(filter(str.isdigit, text)))
                    except Exception as e:
                        print(f"SQM parse error: {e}")

        img_tag = card.find("img", src=True)
        image_url = img_tag['src'] if img_tag else None

        print(f"Listing: {title}, Price: {price}, Sqm: {sqm}")

        if price and sqm and price_min <= price <= price_max and sqm >= sqm_min:
            listings.append({
                "id": listing_id,
                "title": title,
                "link": link,
                "price": price,
                "sqm": sqm,
                "image_url": image_url,
                "city": city
            })

    print(f"Filtered listings count: {len(listings)}")
    return listings

def send_listing(bot, chat_id, listing):
    print(f"Sending listing: {listing['title']} to chat {chat_id}")
    text = (f"🏠 {listing['title']}\n"
            f"📍 Città: {listing['city']}\n"
            f"💶 Prezzo: {listing['price']} €\n"
            f"📐 Mq: {listing['sqm']}\n"
            f"🔗 [Link all'annuncio]({listing['link']})")

    try:
        if listing['image_url']:
            bot.send_photo(chat_id=chat_id, photo=listing['image_url'], caption=text, parse_mode='Markdown')
        else:
            bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
    except Exception as e:
        print(f"Error sending listing: {e}")
        # fallback to text only
        bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')

def search_and_alert(bot, chat_id, cities, price_min, price_max, sqm_min):
    cities_list = [c.strip() for c in cities.split(',')]
    for city in cities_list:
        listings = scrape_listings(city, price_min, price_max, sqm_min)
        if not listings:
            print(f"No listings found for {city} with filters")
        for listing in listings:
            if not listing_already_sent(chat_id, listing['id']):
                print(f"Sending listing {listing['id']} to chat {chat_id}")
                send_listing(bot, chat_id, listing)
                mark_listing_sent(chat_id, listing['id'])
            else:
                print(f"Listing {listing['id']} already sent to chat {chat_id}")

def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    default_cities = "pagnacco,martignacco,colloredo-di-monte-albano,moruzzo,reana-del-rojale,tricesimo,tavagnacco"
    default_price_min = 100000
    default_price_max = 350000
    default_sqm_min = 100

    save_user(chat_id, default_cities, default_price_min, default_price_max, default_sqm_min)
    update.message.reply_text(
        f"Benvenuto! Filtri impostati:\n"
        f"Città: {default_cities}\n"
        f"Prezzo: {default_price_min}-{default_price_max} €\n"
        f"Mq min: {default_sqm_min}\n"
        f"Usa /cercaora per cercare ora."
    )

def cercaora(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    users = get_users()
    user = next((u for u in users if u[0] == chat_id), None)
    if not user:
        update.message.reply_text("Non hai filtri impostati, usa /start.")
        return
    cities, price_min, price_max, sqm_min = user[1], user[2], user[3], user[4]
    update.message.reply_text(f"Cerco annunci per città: {cities}...")

    search_and_alert(bot, chat_id, cities, price_min, price_max, sqm_min)

# Optional: scheduled job to run search_and_alert for all users every 3 hours
def scheduled_job(bot):
    while True:
        print(f"Scheduled job running at {datetime.now()}...")
        users = get_users()
        for user in users:
            chat_id, cities, price_min, price_max, sqm_min = user
            search_and_alert(bot, chat_id, cities, price_min, price_max, sqm_min)
        time.sleep(3 * 3600)

def main():
    init_db()
    updater = Updater(token=TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Register commands so they appear in Telegram’s slash menu
    commands = [
        BotCommand("start", "Avvia il bot e imposta i filtri di default"),
        BotCommand("cercaora", "Cerca annunci ora con i filtri attivi"),
        # Add setcity, setprice, setsqm handlers if you want them later
    ]
    updater.bot.set_my_commands(commands)

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('cercaora', cercaora))

    # Uncomment if you want to run the scheduled job in a thread (not recommended on Render)
    # threading.Thread(target=scheduled_job, args=(bot,), daemon=True).start()

    updater.start_polling()
    print("Bot attivo...")
    updater.idle()

if __name__ == "__main__":
    main()
