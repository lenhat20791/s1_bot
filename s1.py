import logging
import json
import csv
import os
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext, JobQueue
from binance.client import Client

# Configurations
TOKEN = "7637023247:AAG_utVTC0rXyfute9xsBdh-IrTUE3432o8"
BINANCE_API_KEY = "aVim4czsoOzuLxk0CsEsV0JwE58OX90GRD8OvDfT8xH2nfSEC0mMnMCVrwgFcSEi"
BINANCE_API_SECRET = "rIQ2LLUtYWBcXt5FiMIHuXeeDJqeREbvw8r9NlTJ83gveSAvpSMqd1NBoQjAodC4"
CHAT_ID = 7662080576
LOG_FILE = "bot_log.json"
PATTERN_LOG_FILE = "pattern_log.txt"

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure log files exist
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

if not os.path.exists(PATTERN_LOG_FILE):
    with open(PATTERN_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== Pattern Log Initialized ===\n")

# Store pivot data
detected_pivots = []  # Stores last 15 pivots
user_provided_pivots = []  # Stores pivots provided via /moc command

# Initialize Binance Client
binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

def save_log(data, filename):
    """ Save log messages to a text file """
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [INFO] - {message}\n")

def get_binance_price(context: CallbackContext):
    """ Fetches high and low prices for the last 5-minute candlestick """
    try:
        klines = binance_client.futures_klines(symbol="BTCUSDT", interval="5m", limit=2)
        last_candle = klines[-2]  # Ensure we get the closed candle
        high_price = float(last_candle[2])
        low_price = float(last_candle[3])

        detect_pivot(high_price, "H")
        detect_pivot(low_price, "L")
    except Exception as e:
        logger.error(f"Binance API Error: {e}")
        save_log(f"Binance API Error: {e}", PATTERN_LOG_FILE)

def detect_pivot(price, price_type):
    """ Determines pivot points using user-provided and real-time data."""
    global detected_pivots, user_provided_pivots

    combined_pivots = user_provided_pivots + detected_pivots
    if len(combined_pivots) < 5:
        pivot_type = "HL"  # Default for first few data points
    else:
        a, b, c, d, e = [p["price"] for p in combined_pivots[-5:]]
        
        if a > b and a > c and c > b and c > d:
            pivot_type = "HH"
        elif a < b and a < c and c < b and c < d:
            pivot_type = "LL"
        elif a >= c and (b > c and b > d and d > c and d > e):
            pivot_type = "HL"
        elif a <= c and (b < c and b < d and d < c and d < e):
            pivot_type = "LH"
        else:
            pivot_type = combined_pivots[-1]["type"]

    detected_pivots.append({"type": pivot_type, "price": price, "time": datetime.now().strftime("%H:%M")})
    if len(detected_pivots) > 15:
        detected_pivots.pop(0)

    save_log(f"Xác định {pivot_type} - Giá: {price}", PATTERN_LOG_FILE)
    draw_pattern_chart()
    if check_pattern():
        send_alert()

def draw_pattern_chart():
    """ Generates an ASCII chart of detected pivot points """
    lines = []
    for p in detected_pivots[-10:]:
        if p["type"] == "HH":
            lines.append(f"    /{p['type']} \\")
        elif p["type"] == "LL":
            lines.append(f"    \\{p['type']} /")
        elif p["type"] == "HL":
            lines.append(f"      {p['type']}")
        elif p["type"] == "LH":
            lines.append(f"      {p['type']}")

    save_log("\n".join(lines), PATTERN_LOG_FILE)
    
def check_pattern():
    """ Checks if detected pivots match predefined patterns."""
    patterns = {
        "bullish_reversal": [
            "HH", "HL", "HH", "HL", "HH",
            "LH", "HL", "HH", "HL", "HH",
            "HH", "HH", "HH",
            "HH", "HL", "HH", "HH"
        ],
        "bearish_reversal": [
            "LL", "LL", "LH", "LL",
            "LL", "LH", "LL", "LH", "LL",
            "LL", "LL", "LL",
            "LL", "LH", "LL", "LH", "LL",
            "LL", "LH", "LL"
        ]
    }
    
    last_pivots = [p["type"] for p in detected_pivots]
    for pattern_name, sequence in patterns.items():
        if last_pivots[-len(sequence):] == sequence:
            save_log(f"Xác định mẫu hình: {pattern_name} ({', '.join(sequence)})", PATTERN_LOG_FILE)
            return True
    return False

def send_alert():
    """ Sends an alert message to Telegram."""
    bot = Bot(token=TOKEN)
    bot.send_message(chat_id=CHAT_ID, text="⚠️ Pattern Detected! Check the market.")

def moc(update: Update, context: CallbackContext):
    """ Handles the /moc command to receive pivot points."""
    global user_provided_pivots
    args = context.args
    
    if len(args) < 6:
        update.message.reply_text("Invalid format. Use: /moc btc lh 82000 14h20 hl 81000 14h30 hh 83000 14h50")
        return
    
    new_pivot = {
        "type": args[1],
        "price": float(args[2]),
        "time": args[3]
    }
    user_provided_pivots.append(new_pivot)

    if len(user_provided_pivots) > 15:
        user_provided_pivots.pop(0)

    save_log(f"User Pivots Updated: {user_provided_pivots}", LOG_FILE)
    save_log(f"User Pivots Updated: {user_provided_pivots}", PATTERN_LOG_FILE)

    update.message.reply_text(f"✅ Đã nhận các mốc: {user_provided_pivots}")
    logger.info(f"User Pivots Updated: {user_provided_pivots}")

def main():
    """ Main entry point to start the bot."""
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    job_queue = updater.job_queue
    
    dp.add_handler(CommandHandler("moc", moc))
    
    # Schedule price updates every 5 minutes
    job_queue.run_repeating(get_binance_price, interval=300, first=0)
    
    print("Bot is running...")
    logger.info("Bot started successfully.")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
