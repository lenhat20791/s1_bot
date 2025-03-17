import logging
import json
import csv
import os
import time
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext, JobQueue
from binance.client import Client
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference

# Configurations
TOKEN = "7637023247:AAG_utVTC0rXyfute9xsBdh-IrTUE3432o8"
BINANCE_API_KEY = "aVim4czsoOzuLxk0CsEsV0JwE58OX90GRD8OvDfT8xH2nfSEC0mMnMCVrwgFcSEi"
BINANCE_API_SECRET = "rIQ2LLUtYWBcXt5FiMIHuXeeDJqeREbvw8r9NlTJ83gveSAvpSMqd1NBoQjAodC4"
CHAT_ID = 7662080576
LOG_FILE = "bot_log.json"
PATTERN_LOG_FILE = "pattern_log.txt"
DEBUG_LOG_FILE = "debug_log.txt"
EXCEL_FILE = "pivots.xlsx"

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure log files exist
for file in [LOG_FILE, PATTERN_LOG_FILE, DEBUG_LOG_FILE]:
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            f.write("=== Log Initialized ===\n")


# Store pivot data
detected_pivots = []  # Stores last 15 pivots
user_provided_pivots = []  # Stores pivots provided via /moc command

# Initialize Binance Client
binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

def save_log(log_message, filename):
    """ Save log messages to a text file """
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [INFO] - {log_message}\n")

def save_to_excel():
    """ Saves pivot data to an Excel file with a chart."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Time", "Type", "Price"])
    
    for pivot in detected_pivots:
        ws.append([pivot["time"], pivot["type"], pivot["price"]])
    
    chart = LineChart()
    data = Reference(ws, min_col=3, min_row=2, max_row=len(detected_pivots) + 1)
    categories = Reference(ws, min_col=1, min_row=2, max_row=len(detected_pivots) + 1)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(categories)
    chart.title = "Pivot Points"
    chart.x_axis.title = "Time"
    chart.y_axis.title = "Price"
    ws.add_chart(chart, "E5")
    
    wb.save(EXCEL_FILE)
    save_log("Pivot data saved to Excel", DEBUG_LOG_FILE)
    
def get_binance_price(context: CallbackContext):
    """ Fetches high and low prices for the last 5-minute candlestick """
    try:
        # Chờ đến thời điểm chính xác (00, 05, 10, ..., 55)
        now = datetime.utcnow()
        seconds_to_wait = (5 - (now.minute % 5)) * 60 - now.second
        time.sleep(seconds_to_wait)
        
        # Lấy dữ liệu nến 5m đã đóng hoàn toàn
        klines = binance_client.futures_klines(symbol="BTCUSDT", interval="5m", limit=2)
        last_candle = klines[-2]  # Ensure we get the closed candle
        high_price = float(last_candle[2])
        low_price = float(last_candle[3])

        save_log(f"Thu thập dữ liệu nến 5m: Cao nhất = {high_price}, Thấp nhất = {low_price}", DEBUG_LOG_FILE)
        detect_pivot(high_price, "H")
        detect_pivot(low_price, "L")
        save_to_excel()
    except Exception as e:
        logger.error(f"Binance API Error: {e}")
        save_log(f"Binance API Error: {e}", DEBUG_LOG_FILE)

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
    """ Handles the /moc command to receive multiple pivot points and resets logic."""
    global user_provided_pivots, detected_pivots
    args = context.args
    
    logger.info(f"Received /moc command with args: {args}")
    save_log(f"Received /moc command with args: {args}", DEBUG_LOG_FILE)
    
    if len(args) < 4 or (len(args) - 1) % 3 != 0:
        update.message.reply_text("⚠️ Sai định dạng! Dùng: /moc btc lh 82000 14h20 hl 81000 14h30 hh 83000 14h50")
        return
    
    asset = args[0].lower()
    if asset != "btc":
        update.message.reply_text("⚠️ Chỉ hỗ trợ BTC! Ví dụ: /moc btc lh 82000 14h20 hl 81000 14h30 hh 83000 14h50")
        return
        
    # **Xóa dữ liệu cũ** trước khi cập nhật mốc mới
    user_provided_pivots.clear()
    detected_pivots.clear()
    
    # Ghi nhận các mốc mới
    for i in range(1, len(args), 3):
        try:
            pivot_type = args[i]
            price = float(args[i + 1])
            time = args[i + 2]
            user_provided_pivots.append({"type": pivot_type, "price": price, "time": time})
            save_log(f"Nhận mốc {pivot_type} - Giá: {price} - Thời gian: {time}", DEBUG_LOG_FILE)
        except ValueError:
            update.message.reply_text(f"⚠️ Lỗi: Giá phải là số hợp lệ! ({args[i + 1]})")
            return
    
    # Giới hạn 15 mốc gần nhất
    if len(user_provided_pivots) > 15:
        user_provided_pivots = user_provided_pivots[-15:]

    # **Ghi đè dữ liệu vào pattern log**
    with open(PATTERN_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== Pattern Log Reset ===\n")

    save_log(f"User Pivots Updated: {user_provided_pivots}", LOG_FILE)
    save_log(f"User Pivots Updated: {user_provided_pivots}", PATTERN_LOG_FILE)
    save_to_excel()

    # Phản hồi cho người dùng
    update.message.reply_text(f"✅ Đã nhận các mốc: {user_provided_pivots}")
    logger.info(f"User Pivots Updated: {user_provided_pivots}")

def main():
    """ Main entry point to start the bot."""
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    job_queue = updater.job_queue
    
    dp.add_handler(CommandHandler("moc", moc))
    
    # Chờ đến thời điểm gần nhất (00, 05, 10, ..., 55)
    now = datetime.utcnow()
    seconds_to_wait = (5 - (now.minute % 5)) * 60 - now.second
    time.sleep(seconds_to_wait)
    
    job_queue.run_repeating(get_binance_price, interval=300, first=0)  # 5 phút
    
    print("Bot is running...")
    logger.info("Bot started successfully.")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
