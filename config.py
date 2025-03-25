import os
from load_env import load_env_file

# Đọc file .env (hoặc info.env)
load_env_file('info.env')

# Lấy biến môi trường
TOKEN = os.environ.get("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")
CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID"))
ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")
CURRENT_USER = os.environ.get("CURRENT_USER", "lenhat20791")
CURRENT_UTC_TIME = os.environ.get("CURRENT_UTC_TIME", "2025-03-24 01:41:50")

# Các đường dẫn file log - sử dụng đường dẫn Windows
LOG_FILE = "logs\\bot_log.json"
PATTERN_LOG_FILE = "logs\\pattern_log.txt"
DEBUG_LOG_FILE = "logs\\debug.log"
EXCEL_FILE = "data\\pivots.xlsx"