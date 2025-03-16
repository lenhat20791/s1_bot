import time
import threading
from datetime import datetime
from telebot import TeleBot, types
import requests
import logging
import json
import os
import sys
import traceback

# Thiết lập logging cơ bản trước khi khởi tạo bot
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(threadName)s - %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

class PricePatternAnalyzer:
        def __init__(self, max_bars=500):
                self.max_bars = max_bars
                self.price_history = []
                self.pivots = []
                self.patterns = {
                    "mẫu hình tăng để giảm": [
                        ["HH", "HL", "HH", "HL", "HH"],
                        ["LH", "HL", "HH", "HL", "HH"],
                        ["HH", "HH", "HH"],
                        ["HH", "HL", "HH", "HH"]
                    ],
                    "mẫu hình giảm để tăng": [
                        ["LL", "LL", "LH", "LL"],
                        ["LL", "LH", "LL", "LH", "LL"],
                        ["LL", "LL", "LL"],
                        ["LL", "LH", "LL", "LH", "LL"],
                        ["LL", "LH", "LL"]
                    ]
                }

        def find_pivots(self, prices, lb=5, rb=5):
                """Tìm các điểm pivot (High và Low)"""
                pivots = []
                for i in range(lb, len(prices) - rb):
                    # Kiểm tra Pivot High
                    is_ph = True
                    for j in range(i-lb, i+rb+1):
                        if j != i and prices[j] >= prices[i]:
                            is_ph = False
                            break
                    if is_ph:
                        pivots.append(("H", prices[i], i))
                        continue

                    # Kiểm tra Pivot Low
                    is_pl = True
                    for j in range(i-lb, i+rb+1):
                        if j != i and prices[j] <= prices[i]:
                            is_pl = False
                            break
                    if is_pl:
                        pivots.append(("L", prices[i], i))

                return pivots

        def classify_pivots(self, pivots):
                """Phân loại các điểm pivot thành HH, HL, LH, LL"""
                classified = []
                for i in range(1, len(pivots)):
                    current = pivots[i]
                    previous = pivots[i-1]
                    
                    if current[0] == "H":
                        if current[1] > previous[1]:
                            classified.append("HH")
                        else:
                            classified.append("LH")
                    else:  # current[0] == "L"
                        if current[1] < previous[1]:
                            classified.append("LL")
                        else:
                            classified.append("HL")
                            
                return classified

        def find_patterns(self, classified_pivots):
                """Tìm các mẫu hình đã định nghĩa"""
                found_patterns = []
                
                # Chuyển classified_pivots thành chuỗi để dễ so sánh
                pivot_string = ",".join(classified_pivots)
                
                # Kiểm tra từng nhóm mẫu hình
                for pattern_group, patterns in self.patterns.items():
                    for pattern in patterns:
                        pattern_string = ",".join(pattern)
                        if pattern_string in pivot_string:
                            found_patterns.append(pattern_group)
                            break  # Nếu tìm thấy 1 mẫu trong nhóm, chuyển sang nhóm khác
                            
                return list(set(found_patterns))  # Loại bỏ các mẫu trùng lặp

        def analyze(self, new_price):
                """Phân tích giá mới và trả về các mẫu hình tìm thấy"""
                self.price_history.append(new_price)
                if len(self.price_history) > self.max_bars:
                    self.price_history.pop(0)
                    
                if len(self.price_history) < 10:  # Cần ít nhất 10 giá để phân tích
                    return []
                    
                pivots = self.find_pivots(self.price_history)
                classified_pivots = self.classify_pivots(pivots)
                return self.find_patterns(classified_pivots)
        
class PriceAlertBot:
    def __init__(self):
        try:
            # Khởi tạo các thông số cơ bản
            self.API_TOKEN = '7637023247:AAG_utVTC0rXyfute9xsBdh-IrTUE3432o8'
            self.CHAT_ID = 7662080576
            self.EXCHANGE_RATE_API_KEY = '6d4a617a86b3985f2dc473b4'
            
            # Tạo thư mục logs nếu chưa có
            os.makedirs('logs', exist_ok=True)
            
            # Thiết lập file logging
            log_file = f'logs/bot_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.log'
            file_handler = logging.FileHandler(log_file, 'w', 'utf-8')
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s [%(levelname)s] %(threadName)s - %(filename)s:%(lineno)d - %(message)s')
            )
            logging.getLogger().addHandler(file_handler)
            
            logging.info("=== KHỞI TẠO BOT ===")
            
            # Khởi tạo bot
            logging.info("Đang khởi tạo bot instance...")
            self.bot = TeleBot(self.API_TOKEN)
            
            # Kiểm tra kết nối
            bot_info = self.bot.get_me()
            logging.info(f"Kết nối thành công tới bot: {bot_info.username}")
            
            # Khởi tạo biến theo dõi giá
            self.gia_muc_tieu = {'BTC': None, 'AUD': None}
            self.dang_cho_nhap_gia = {}
            
            # Thiết lập handlers
            self.setup_handlers()
            
            # Thêm các analyzers mới vào cuối __init__
            self.btc_analyzer = PricePatternAnalyzer()
            self.aud_analyzer = PricePatternAnalyzer()
            
            # Thiết lập handlers
            self.setup_handlers()
            
            logging.info("Khởi tạo bot thành công")
            
        except Exception as e:
            logging.error(f"Lỗi khởi tạo bot: {str(e)}")
            logging.error(traceback.format_exc())
            raise

    def setup_handlers(self):
        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            self.bot.reply_to(message, 
                "Xin chào! Tôi là bot cảnh báo giá.\n"
                "Sử dụng /btc để đặt cảnh báo BTC\n"
                "Sử dụng /aud để đặt cảnh báo AUD\n"
                "Sử dụng /reset để xóa tất cả cảnh báo")

        @self.bot.message_handler(commands=['reset'])
        def handle_reset(message):
            try:
                # Lưu số lượng cảnh báo trước khi reset
                btc_alert = "BTC" if self.gia_muc_tieu['BTC'] else None
                aud_alert = "AUD" if self.gia_muc_tieu['AUD'] else None
                alerts_to_reset = [x for x in [btc_alert, aud_alert] if x]
                
                # Reset tất cả giá mục tiêu về None
                self.gia_muc_tieu = {'BTC': None, 'AUD': None}
                self.dang_cho_nhap_gia = {}
                
                # Tạo thông báo phản hồi
                if alerts_to_reset:
                    response = f"✅ Đã xóa {len(alerts_to_reset)} cảnh báo giá: {', '.join(alerts_to_reset)}"
                    logging.info(f"Đã reset cảnh báo giá: {alerts_to_reset}")
                else:
                    response = "ℹ️ Không có cảnh báo giá nào để xóa"
                    logging.info("Lệnh reset được gọi khi không có cảnh báo giá")
                
                self.bot.reply_to(message, response)
                
            except Exception as e:
                error_msg = f"❌ Lỗi khi reset cảnh báo giá: {str(e)}"
                logging.error(error_msg)
                logging.error(traceback.format_exc())
                self.bot.reply_to(message, error_msg)

        @self.bot.message_handler(commands=['btc'])
        def handle_btc(message):
            try:
                price = self.get_btc_price()
                if price:
                    self.dang_cho_nhap_gia[message.chat.id] = 'BTC'
                    self.bot.reply_to(message, 
                        f"Giá BTC hiện tại: ${price:,.2f}\n"
                        f"Vui lòng nhập giá mục tiêu:")
                else:
                    self.bot.reply_to(message, "Không thể lấy giá BTC. Vui lòng thử lại sau.")
            except Exception as e:
                logging.error(f"Lỗi xử lý lệnh BTC: {str(e)}")

        @self.bot.message_handler(commands=['aud'])
        def handle_aud(message):
            try:
                price = self.get_aud_price()
                if price:
                    self.dang_cho_nhap_gia[message.chat.id] = 'AUD'
                    self.bot.reply_to(message,
                        f"Giá USD/AUD hiện tại: {price:.5f}\n"
                        f"Vui lòng nhập giá mục tiêu:")
                else:
                    self.bot.reply_to(message, "Không thể lấy giá AUD. Vui lòng thử lại sau.")
            except Exception as e:
                logging.error(f"Lỗi xử lý lệnh AUD: {str(e)}")

        @self.bot.message_handler(func=lambda message: True)
        def handle_price_input(message):
            try:
                chat_id = message.chat.id
                if chat_id not in self.dang_cho_nhap_gia:
                    return

                currency = self.dang_cho_nhap_gia[chat_id]
                try:
                    target_price = float(message.text)
                    self.gia_muc_tieu[currency] = target_price
                    self.bot.reply_to(message, 
                        f"Đã đặt cảnh báo cho {currency} tại mức: {target_price:.5f}")
                except ValueError:
                    self.bot.reply_to(message, "Giá không hợp lệ. Vui lòng nhập một số.")
                
                del self.dang_cho_nhap_gia[chat_id]
                
            except Exception as e:
                logging.error(f"Lỗi xử lý nhập giá: {str(e)}")

    def get_btc_price(self):
        try:
            response = requests.get(
                'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT',
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            price = float(data['price'])
            logging.debug(f"Giá BTC: {price}")
            return price
        except Exception as e:
            logging.error(f"Lỗi lấy giá BTC: {str(e)}")
            return None

    def get_aud_price(self):
        try:
            response = requests.get(
                f'https://v6.exchangerate-api.com/v6/{self.EXCHANGE_RATE_API_KEY}/latest/USD',
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Chuyển đổi từ AUD/USD sang USD/AUD
            aud_usd = float(data['conversion_rates']['AUD'])
            usd_aud = 1 / aud_usd
            
            logging.debug(f"Giá USD/AUD: {usd_aud:.5f}")
            return usd_aud
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Lỗi kết nối API AUD: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Lỗi lấy giá AUD: {str(e)}")
            return None

    def monitor_prices(self):
                logging.info("Bắt đầu theo dõi giá...")
                
                while True:
                    try:
                        # Kiểm tra BTC
                        price = self.get_btc_price()
                        if price:
                            # Phân tích mẫu hình
                            patterns = self.btc_analyzer.analyze(price)
                            for pattern in patterns:
                                self.bot.send_message(
                                    self.CHAT_ID,
                                    f"🔄 Cảnh báo BTC: {pattern}"
                                )
                            
                            # Kiểm tra giá mục tiêu
                            if self.gia_muc_tieu['BTC'] and price >= self.gia_muc_tieu['BTC']:
                                self.bot.send_message(
                                    self.CHAT_ID,
                                    f"🚨 Cảnh báo BTC đạt mục tiêu: ${price:,.2f}"
                                )
                                self.gia_muc_tieu['BTC'] = None

                        # Kiểm tra AUD
                        price = self.get_aud_price()
                        if price:
                            # Phân tích mẫu hình
                            patterns = self.aud_analyzer.analyze(price)
                            for pattern in patterns:
                                self.bot.send_message(
                                    self.CHAT_ID,
                                    f"🔄 Cảnh báo AUD: {pattern}"
                                )
                            
                            # Kiểm tra giá mục tiêu
                            if self.gia_muc_tieu['AUD'] and price >= self.gia_muc_tieu['AUD']:
                                self.bot.send_message(
                                    self.CHAT_ID,
                                    f"🚨 Cảnh báo USD/AUD đạt mục tiêu: {price:.5f}"
                                )
                                self.gia_muc_tieu['AUD'] = None

                    except Exception as e:
                        logging.error(f"Lỗi theo dõi giá: {str(e)}")

                    time.sleep(60)


    def run(self):
        try:
            # Khởi động thread theo dõi giá
            monitor_thread = threading.Thread(
                target=self.monitor_prices,
                daemon=True,
                name="PriceMonitor"
            )
            monitor_thread.start()
            logging.info("Đã khởi động thread theo dõi giá")
            
            # Thông báo khởi động
            self.bot.send_message(self.CHAT_ID, "Bot đã sẵn sàng!")
            logging.info("Đã gửi thông báo khởi động")
            
            # Bắt đầu polling
            logging.info("Bắt đầu polling...")
            self.bot.infinity_polling(timeout=10, long_polling_timeout=5)
            
        except Exception as e:
            logging.error(f"Lỗi chạy bot: {str(e)}")
            raise

if __name__ == "__main__":
    try:
        bot = PriceAlertBot()
        bot.run()
    except KeyboardInterrupt:
        logging.info("Dừng bot bởi người dùng")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Lỗi không xác định: {str(e)}")
        logging.error(traceback.format_exc())
        sys.exit(1)