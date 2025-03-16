import time
import threading
from datetime import datetime, timezone, timedelta
import ccxt
import numpy as np
from telebot import TeleBot, types
import requests
import logging
import json
import os
import sys
import traceback

def get_vietnam_time(utc_time):
    """Chuyển đổi thời gian từ UTC sang giờ Việt Nam"""
    if isinstance(utc_time, str):
        utc_time = datetime.strptime(utc_time, '%Y-%m-%d %H:%M:%S')
    vietnam_tz = timezone(timedelta(hours=7))
    return utc_time.replace(tzinfo=timezone.utc).astimezone(vietnam_tz)

def get_next_5min_mark():
    """Lấy mốc 5 phút tiếp theo"""
    now = datetime.now(timezone.utc)
    minutes = now.minute
    next_5min = ((minutes // 5) + 1) * 5
    if next_5min == 60:
        next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_time = now.replace(minute=next_5min, second=0, microsecond=0)
    return next_time

# Thiết lập logging cơ bản trước khi khởi tạo bot
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(threadName)s - %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

class S1Bot:
    def __init__(self):
        print("Bot khởi tạo")
        self.price_history = []
        self.time_history = []
        self.logger = self.setup_logger()
        self.btc_analyzer = BTCAnalyzer()
        
    def setup_logger(self):
        import logging
        logger = logging.getLogger('S1Bot')
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger
        
    def find_pivots(self, prices, times, lb=3, rb=3, tolerance=0.0001):
        """Tìm các điểm pivot (High và Low) với timestamp"""
        pivots = []
        for i in range(lb, len(prices) - rb):
            is_pivot = True
            for j in range(1, lb + 1):
                if prices[i] <= prices[i - j] + tolerance or prices[i] <= prices[i + j] + tolerance:
                    is_pivot = False
                    break
            if is_pivot:
                pivots.append((times[i], prices[i], i, 'High'))
                continue

            is_pivot = True
            for j in range(1, lb + 1):
                if prices[i] >= prices[i - j] - tolerance or prices[i] >= prices[i + j] - tolerance:
                    is_pivot = False
                    break
            if is_pivot:
                pivots.append((times[i], prices[i], i, 'Low'))

        return pivots

    def classify_pivots(self, pivots):
        """Phân loại các điểm pivot"""
        classified_pivots = []
        for pivot in pivots:
            if pivot[3] == 'High':
                classified_pivots.append((pivot[0], pivot[1], pivot[2], 'HH'))
            elif pivot[3] == 'Low':
                classified_pivots.append((pivot[0], pivot[1], pivot[2], 'LL'))
        return classified_pivots
    def find_patterns(self, classified_pivots):
        """Tìm kiếm mẫu hình dựa trên các điểm pivot đã phân loại"""
        patterns = []
        # Giả sử bạn có logic để tìm mẫu hình từ classified_pivots
        return patterns
        
    def analyze_patterns(self):
        """Phân tích mẫu hình dựa trên pivot points"""
        self.logger.info("\nTìm kiếm điểm pivot...")
        pivots = self.find_pivots(self.price_history, self.time_history)
        if not pivots:
            self.logger.info("❌ Không tìm thấy điểm pivot")
            return []

        self.logger.info("\nPhân loại các điểm pivot...")
        classified_pivots = self.classify_pivots(pivots)
        if not classified_pivots:
            self.logger.info("❌ Không có mẫu hình để phân loại")
            return []

        self.logger.info("\nTìm kiếm mẫu hình...")
        patterns = self.find_patterns(classified_pivots)

        if patterns:
            self.logger.info(f"✅ Đã tìm thấy mẫu hình: {patterns}")
        else:
            self.logger.info("❌ Không phát hiện mẫu hình")

        return patterns

    def should_send_alert(self, new_patterns):
        """Xác định xem có nên gửi cảnh báo dựa trên các mẫu hình mới"""
        if not new_patterns:
            return False
        if hasattr(self, 'last_pattern') and self.last_pattern == new_patterns[-1]:
            return False
        self.last_pattern = new_patterns[-1]
        return True

class PricePatternAnalyzer:
        def __init__(self, max_bars=200):
            self.max_bars = max_bars
            self.price_history = []
            self.time_history = []
            self.pivots = []
            self.last_pattern = None
            self.pivot_history = []  # Lưu tối đa 15 đỉnh đáy gần nhất
            self.historical_pivots = []  # Lưu các pivot points được cung cấp
            self.last_sync_time = None   # Thời điểm đồng bộ cuối cùng
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
            # Tạo logger riêng cho pattern analyzer
            self.logger = logging.getLogger('PatternAnalyzer')
            self.logger.setLevel(logging.DEBUG)
                
            # Tạo thư mục logs nếu chưa có
            os.makedirs('logs', exist_ok=True)
                
            # Tạo file handler cho pattern analysis
            pattern_handler = logging.FileHandler(
                f'logs/pattern_analysis_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.log',
                encoding='utf-8'
            )
            pattern_handler.setFormatter(
                logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')
            )
            self.logger.addHandler(pattern_handler)
            self.logger.info("=== Pattern Analyzer Started ===")

        def find_pivots(
            self, prices: list[float], times: list[str], lb: int = 3, rb: int = 3, tolerance: float = 0.0001
        ) -> list[tuple[str, float, int, str]]:
            """Tìm các điểm pivot (High và Low) với timestamp"""
            pivots = []
            for i in range(lb, len(prices) - rb):
                current_price = prices[i]

                # Kiểm tra Pivot High
                is_ph = True
                for j in range(i-lb, i+rb+1):
                    if j != i and prices[j] >= (current_price * (1 - tolerance)):
                        is_ph = False
                        break
                if is_ph:
                    pivots.append(("H", prices[i], i, times[i]))
                    vn_time = get_vietnam_time(times[i])
                    self.logger.info(
                        f"Found Pivot High: ${current_price:,.2f} at {vn_time.strftime('%Y-%m-%d %H:%M:%S')} VN"
                    )
                    continue

                # Kiểm tra Pivot Low
                is_pl = True
                for j in range(i-lb, i+rb+1):
                    if j != i and prices[j] <= (current_price * (1 + tolerance)):
                        is_pl = False
                        break
                if is_pl:
                    pivots.append(("L", prices[i], i, times[i]))
                    vn_time = get_vietnam_time(times[i])
                    self.logger.info(
                        f"Found Pivot Low: ${current_price:,.2f} at {vn_time.strftime('%Y-%m-%d %H:%M:%S')} VN"
                    )
            # Thêm logging tổng hợp
            if pivots:
                self.logger.info(f"\nTìm thấy {len(pivots)} điểm pivot:")
                for pivot_type, price, _, time in pivots:
                    vn_time = get_vietnam_time(time)
                    pivot_name = "High" if pivot_type == "H" else "Low"
                    self.logger.info(
                        f"- Pivot {pivot_name}: ${price:,.2f} tại {vn_time.strftime('%H:%M:%S')}"
                    )
            # Sau khi thêm pivot mới vào danh sách pivots
            if len(pivots) >= 15:
                recent_pivots = pivots[-15:]
            else:
                recent_pivots = pivots
            
            self.logger.info("Thống kê 15 đỉnh đáy gần nhất:")
            for pivot_type, price, _, time in recent_pivots:
                vn_time = get_vietnam_time(time)
                pivot_name = "High" if pivot_type == "H" else "Low"
                self.logger.info(f"- Pivot {pivot_name}: ${price:,.2f} tại {vn_time.strftime('%H:%M:%S')}")

            return pivots

        def classify_pivots(self, pivots):
            """Phân loại các điểm pivot thành HH, HL, LH, LL với logging"""
            classified = []
            for i in range(1, len(pivots)):
                current = pivots[i]
                previous = pivots[i-1]
                            
                current_time_vn = get_vietnam_time(current[3])
                previous_time_vn = get_vietnam_time(previous[3])
                            
                if current[0] == "H":
                    if current[1] > previous[1]:
                        classified.append("HH")
                        self.logger.info(
                                f"Higher High: ${current[1]:,.2f} at {current_time_vn.strftime('%Y-%m-%d %H:%M:%S')} VN " 
                                f"(Previous: ${previous[1]:,.2f} at {previous_time_vn.strftime('%Y-%m-%d %H:%M:%S')} VN)"
                            )
                    else:
                        classified.append("LH")
                        self.logger.info(
                            f"Lower High: ${current[1]:,.2f} at {current_time_vn.strftime('%Y-%m-%d %H:%M:%S')} VN "
                            f"(Previous: ${previous[1]:,.2f} at {previous_time_vn.strftime('%Y-%m-%d %H:%M:%S')} VN)"
                            )
                else:  # current[0] == "L"
                    if current[1] < previous[1]:
                        classified.append("LL")
                        self.logger.info(
                            f"Lower Low: ${current[1]:,.2f} at {current_time_vn.strftime('%Y-%m-%d %H:%M:%S')} VN "
                            f"(Previous: ${previous[1]:,.2f} at {previous_time_vn.strftime('%Y-%m-%d %H:%M:%S')} VN)"
                        )
                    else:
                        classified.append("HL")
                        self.logger.info(
                            f"Higher Low: ${current[1]:,.2f} at {current_time_vn.strftime('%Y-%m-%d %H:%M:%S')} VN "
                            f"(Previous: ${previous[1]:,.2f} at {previous_time_vn.strftime('%Y-%m-%d %H:%M:%S')} VN)"
                        )
                                    
            return classified

        def find_patterns(self, classified_pivots):
            """Tìm các mẫu hình đã định nghĩa"""
            found_patterns = []
                
            # Chuyển classified_pivots thành chuỗi để dễ so sánh
            pivot_string = ",".join(classified_pivots)
            self.logger.debug(f"Analyzing pivot string: {pivot_string}")
                
            # Kiểm tra từng nhóm mẫu hình
            for pattern_group, patterns in self.patterns.items():
                for pattern in patterns:
                    pattern_string = ",".join(pattern)
                    if pattern_string in pivot_string:
                        found_patterns.append(pattern_group)
                        self.logger.info(f"Found pattern: {pattern_group} (matched: {pattern_string})")
                        break
                            
            return list(set(found_patterns))

        def analyze(self, new_price, timestamp):
            """Phân tích giá mới và trả về các mẫu hình tìm thấy"""
            # Chuyển đổi timestamp sang giờ VN cho logging
            vn_time = get_vietnam_time(timestamp)
        
            # Log mỗi khi có giá mới
            self.logger.info(f"\n=== Bắt đầu phân tích giá lúc {vn_time.strftime('%Y-%m-%d %H:%M:%S')} VN ===")
            self.logger.info(f"Giá mới: ${new_price:,.2f}")
        
            # Tính toán và log biến động giá
            if self.price_history:  # Kiểm tra xem có giá trước đó không
                previous_price = self.price_history[-1]
                price_change = new_price - previous_price
                price_change_percent = (price_change / previous_price) * 100
                change_symbol = "↑" if price_change > 0 else "↓" if price_change < 0 else "→"
                self.logger.info(
                    f"Biến động: {change_symbol} ${price_change:+,.2f} ({price_change_percent:+.2f}%) "
                    f"so với ${previous_price:,.2f}"
                )
            
            # Thêm giá mới vào lịch sử
            self.price_history.append(new_price)
            self.time_history.append(timestamp)
                    
            # Log thông tin về dữ liệu
            self.logger.info(f"Số điểm dữ liệu hiện có: {len(self.price_history)}")
            
            # Kiểm tra và cắt bớt nếu vượt quá max_bars
            if len(self.price_history) > self.max_bars:
                self.price_history.pop(0)
                self.time_history.pop(0)
                self.logger.info(f"Đã cắt bớt dữ liệu xuống {self.max_bars} điểm")
                        
            # Kiểm tra số lượng điểm dữ liệu
            if len(self.price_history) < 10:
                self.logger.info(f"⏳ Đang chờ thêm dữ liệu... (Có: {len(self.price_history)}/10 điểm)")
                self.logger.info("=== Kết thúc phân tích ===\n")
                return []
        
            # Log lịch sử giá gần nhất
            self.log_recent_prices()
        
            # Phân tích patterns
            if self.historical_pivots:
                # Sử dụng historical_pivots làm cơ sở
                patterns = self.analyze_with_historical(new_price, timestamp)
            else:
                # Phân tích thông thường
                patterns = self.analyze_patterns()
        
            self.logger.info("=== Kết thúc phân tích ===\n")
            return patterns

        def log_recent_prices(self):
            """Log 5 giá gần nhất với biến động"""
            self.logger.info("\nLịch sử giá gần nhất:")
            for i, (price, time) in enumerate(zip(self.price_history[-5:], self.time_history[-5:]), 1):
                vn_time = get_vietnam_time(time)
                if i > 1:
                    prev_price = self.price_history[-6+i-1]
                    change = price - prev_price
                    change_percent = (change / prev_price) * 100
                    change_symbol = "↑" if change > 0 else "↓" if change < 0 else "→"
                    self.logger.info(
                        f"{i}. {vn_time.strftime('%H:%M:%S')}: ${price:,.2f} "
                        f"{change_symbol} (${change:+,.2f} | {change_percent:+.2f}%)"
                    )
                else:
                    self.logger.info(f"{i}. {vn_time.strftime('%H:%M:%S')}: ${price:,.2f}")

        def analyze_patterns(self) -> list[str]:
            """Phân tích mẫu hình dựa trên pivot points"""
            # Tìm các điểm pivot
            self.logger.info("\nTìm kiếm điểm pivot...")
            pivots: list[tuple[str, float, int, str]] = self.find_pivots(self.price_history, self.time_history)

            if not pivots:
                self.logger.info("❌ Không tìm thấy điểm pivot")
                return []
        
            # Phân loại các điểm pivot
            self.logger.info("\nPhân loại các điểm pivot...")
            classified_pivots: dict[str, list[tuple[str, float, int, str]]] = self.classify_pivots(pivots)
 
            if not classified_pivots:
                self.logger.info("❌ Không có mẫu hình để phân loại")
                return []
        
            # Tìm kiếm mẫu hình
            self.logger.info("\nTìm kiếm mẫu hình...")
            patterns: list[str] = self.find_patterns(classified_pivots)
        
            if patterns:
                self.logger.info(f"✅ Đã tìm thấy mẫu hình: {patterns}")
            else:
                self.logger.info("❌ Không phát hiện mẫu hình")
        
            return patterns
        def get_historical_price(self, timestamp):
            """Lấy giá từ historical data tại timestamp"""
            try:
                # Nếu chưa có dữ liệu lịch sử, lấy giá hiện tại
                if not self.time_history:
                    current_price = self.get_current_price()
                    if current_price:
                        return current_price
                    return None

                # Tìm index gần nhất với timestamp trong time_history
                closest_index = min(range(len(self.time_history)), 
                                  key=lambda i: abs(self.time_history[i] - timestamp))
                return self.price_history[closest_index]
            except Exception as e:
                self.logger.error(f"Lỗi lấy giá historical: {str(e)}")
                return None
        def get_current_price(self):
            """Lấy giá hiện tại từ Binance"""
            try:
                response = requests.get(
                    'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT',
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                return float(data['price'])
            except Exception as e:
                self.logger.error(f"Lỗi lấy giá hiện tại: {str(e)}")
                return None

        def add_historical_pivot(self, pivot_type, timestamp, price=None):
            """Thêm một pivot point từ lịch sử"""
            try:
                if price is None:
                    price = self.get_historical_price(timestamp)
                
                if price:
                    pivot = {
                        'type': pivot_type.upper(),  # HH, HL, LH, LL
                        'time': timestamp,
                        'price': price
                    }
                    # Kiểm tra xem pivot đã tồn tại chưa
                    for existing_pivot in self.historical_pivots:
                        if (abs(existing_pivot['time'] - timestamp) < timedelta(minutes=5) and 
                            existing_pivot['type'] == pivot_type.upper()):
                            self.logger.warning(
                                f"Pivot {pivot_type.upper()} đã tồn tại tại "
                                f"{existing_pivot['time'].strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                            return False

                    self.historical_pivots.append(pivot)
                    # Sắp xếp theo thời gian
                    self.historical_pivots.sort(key=lambda x: x['time'])
                    self.logger.info(
                        f"Đã thêm {pivot_type.upper()} tại "
                        f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} (${price:,.2f})"
                    )
                    return True
                else:
                    self.logger.error(f"Không thể thêm pivot point: không tìm thấy giá tại {timestamp}")
                    return False
            except Exception as e:
                self.logger.error(f"Lỗi thêm historical pivot: {str(e)}")
                return False

        def analyze_with_historical(self, new_price, timestamp):
            """Phân tích dựa trên historical pivots"""
            patterns = []
            
            try:
                if not self.historical_pivots:
                    return patterns
        
                last_pivot = self.historical_pivots[-1]
                pivot_price = last_pivot['price']
                pivot_type = last_pivot['type']
                
                # So sánh với pivot point cuối cùng
                if pivot_type in ['HH', 'LH']:
                    if new_price > pivot_price:
                        self.logger.info(
                            f"Phát hiện HH mới: ${new_price:,.2f} > ${pivot_price:,.2f}"
                        )
                        patterns.append("mẫu hình tăng để giảm")
                    elif new_price < pivot_price:
                        self.logger.info(
                            f"Phát hiện HL mới: ${new_price:,.2f} < ${pivot_price:,.2f}"
                        )
                elif pivot_type in ['LL', 'HL']:
                    if new_price < pivot_price:
                        self.logger.info(
                            f"Phát hiện LL mới: ${new_price:,.2f} < ${pivot_price:,.2f}"
                        )
                        patterns.append("mẫu hình giảm để tăng")
                    elif new_price > pivot_price:
                        self.logger.info(
                            f"Phát hiện LH mới: ${new_price:,.2f} > ${pivot_price:,.2f}"
                        )
        
            except Exception as e:
                self.logger.error(f"Lỗi phân tích historical: {str(e)}")
            
            return patterns
        
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
            log_file = f'logs/bot_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.log'
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
            
            # Thêm các analyzers
            self.btc_analyzer = PricePatternAnalyzer()
            
            # Thiết lập handlers
            self.setup_handlers()
            
            logging.info("Khởi tạo bot thành công")
            
        except Exception as e:
            logging.error(f"Lỗi khởi tạo bot: {str(e)}")
            logging.error(traceback.format_exc())
            raise

    def monitor_prices(self):
        logging.info("Bắt đầu theo dõi giá...")
        while True:
            try:
                current_time = datetime.now(timezone.utc)
                next_time = get_next_5min_mark()
                wait_seconds = (next_time - current_time).total_seconds()
                        
                # Đợi đến mốc 5 phút tiếp theo
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                        
                # Lấy giá và phân tích tại mốc thời gian chính xác
                current_time = datetime.now(timezone.utc)
                vietnam_time = get_vietnam_time(current_time)
                        
                # Kiểm tra BTC
                price = self.get_btc_price()
                if price:
                    # Thêm biến lưu mẫu hình cuối cùng (chỉ cần khai báo một lần trong __init__)
                    if not hasattr(self, 'last_pattern'):
                        self.last_pattern = None
                    
                    # Phân tích mẫu hình với timestamp
                    patterns = self.btc_analyzer.analyze(float(price), current_time)

                    # Kiểm tra và gửi cảnh báo nếu mẫu hình mới xuất hiện
                    new_patterns = [pattern for pattern in patterns if pattern != self.last_pattern]
                
                    if new_patterns:
                        self.last_pattern = new_patterns[-1]  # Lưu mẫu hình mới nhất
                    
                        # Thống kê 15 điểm pivot gần nhất trước khi gửi cảnh báo
                        log_msg = "📊 Thống kê 15 đỉnh đáy gần nhất:\n"
                        for idx, (ptype, t, p_price) in enumerate(self.pivot_history[::-1]):
                            log_msg += f"{idx+1}. {ptype}: {t} (${p_price})\n"
                        
                        # Ghi log lịch sử pivot
                        logging.info(log_msg.strip())
                    
                        # Gửi cảnh báo mẫu hình kèm thống kê pivot
                        message = (
                            f"🔄 Cảnh báo BTC ({vietnam_time.strftime('%Y-%m-%d %H:%M:%S')} VN)\n"
                            f"Giá hiện tại: ${float(price):,.2f}\n"
                            f"Mẫu hình: {pattern}\n\n"
                            f"{log_msg.strip()}"
                        )
                        self.bot.send_message(self.CHAT_ID, message)
                        logging.info(f"📢Đã gửi cảnh báo mẫu hình: {self.last_pattern}")
                    else:
                        logging.info(f"⚠ Mẫu hình không thay đổi, không gửi cảnh báo.")

                    # Kiểm tra giá mục tiêu
                    if self.gia_muc_tieu['BTC'] and float(price) >= self.gia_muc_tieu['BTC']:
                        self.bot.send_message(
                            self.CHAT_ID,
                            f"🚨 Cảnh báo BTC đạt mục tiêu: ${float(price):,.2f}"
                        )
                        self.gia_muc_tieu['BTC'] = None
            
            except Exception as e:
                logging.error(f"Lỗi theo dõi giá: {str(e)}")
                logging.error(traceback.format_exc())

    def parse_time(self, time_str):
        """Chuyển đổi chuỗi thời gian (vd: 9h40) thành datetime"""
        try:
            hour, minute = map(int, time_str.replace('h', ':').split(':'))
            now = datetime.now(timezone.utc)
            result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Nếu thời gian đã qua trong ngày, lấy của ngày hôm trước
            if result > now:
                result -= timedelta(days=1)
            
            return result
        except:
            raise ValueError("Định dạng thời gian không đúng. Sử dụng format: 9h40")

    def setup_handlers(self):
        @self.bot.message_handler(commands=['start', 'help'])
        def send_welcome(message):
            self.bot.reply_to(message, 
                "Xin chào! Tôi là bot cảnh báo giá.\n"
                "Sử dụng /btc để đặt cảnh báo BTC\n"
                "Sử dụng /aud để đặt cảnh báo AUD\n"
                "Sử dụng /moc để thêm mốc pivot (ví dụ: /moc btc lh 9h40 hl 9h55)\n"
                "Sử dụng /reset để xóa tất cả cảnh báo")

        @self.bot.message_handler(commands=['moc'])
        def handle_moc(message):
            try:
                # Phân tích cú pháp lệnh
                parts = message.text.split()
                if len(parts) < 4 or len(parts) % 2 != 0:
                    self.bot.reply_to(message, 
                        "Cú pháp không đúng!\n"
                        "Ví dụ: /moc btc lh 9h40 hl 9h55")
                    return
        
                symbol = parts[1].upper()
                if symbol != 'BTC':
                    self.bot.reply_to(message, "Hiện tại chỉ hỗ trợ BTC")
                    return
        
                pivots = []
                # Xử lý từng cặp pivot_type và time
                for i in range(2, len(parts), 2):
                    pivot_type = parts[i].upper()
                    time_str = parts[i+1]
                    
                    # Chuyển đổi thời gian
                    try:
                        time_obj = self.parse_time(time_str)
                        pivots.append((pivot_type, time_obj))
                    except ValueError as e:
                        self.bot.reply_to(message, f"Lỗi định dạng thời gian: {str(e)}")
                        return
        
                # Thêm các pivot points vào analyzer
                added_count = 0
                for pivot_type, timestamp in pivots:
                    if self.btc_analyzer.add_historical_pivot(pivot_type, timestamp):
                        added_count += 1
        
                # Phản hồi
                if added_count > 0:
                    response = f"Đã thêm {added_count} mốc cho {symbol}:\n"
                    for pivot_type, timestamp in pivots:
                        response += f"- {pivot_type}: {timestamp.strftime('%H:%M')}\n"
                else:
                    response = "Không thể thêm các mốc. Vui lòng kiểm tra log để biết thêm chi tiết."
                
                self.bot.reply_to(message, response)
        
            except Exception as e:
                logging.error(f"Lỗi xử lý lệnh moc: {str(e)}")
                logging.error(traceback.format_exc())
                self.bot.reply_to(message, f"Có lỗi xảy ra: {str(e)}")

        def handle_moc(self, message):
            """ Xử lý lệnh /moc để lưu LH, HL do người dùng nhập """
            data = message.text.split()
            if len(data) == 4 and data[1].lower() in ["lh", "hl", "ll", "hh"]:
                time_input = data[2]
                price = float(data[3])
                self.pivot_history.append((data[1].upper(), time_input, price))
                self.pivot_history = self.pivot_history[-15:]  # Giữ 15 giá trị gần nhất
                self.bot.send_message(message.chat.id, f"✅ Đã lưu {data[1].upper()} tại {time_input}: ${price}")

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
