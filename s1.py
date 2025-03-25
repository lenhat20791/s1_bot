# S1 Bot - Phiên bản Production
# Tối ưu hóa từ phiên bản test

import logging
import json
import pandas as pd
import os
import time
import pytz
import traceback
import sys
from datetime import datetime, timedelta
from telegram import Update, Bot, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext, JobQueue, ConversationHandler, MessageHandler, Filters
from binance.client import Client
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.axis import DateAxis
from openpyxl.chart.marker import Marker
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from pathlib import Path
from default_pivots import initialize_default_pivots

# Đảm bảo hỗ trợ UTF-8 cho đầu ra tiêu chuẩn
if sys.stdout.encoding != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
    
# Tạo các thư mục cần thiết
for folder in ["logs", "data", "backup"]:
    Path(folder).mkdir(exist_ok=True)
    
# Cấu hình từ file 
TOKEN = os.environ.get("TELEGRAM_TOKEN", "7637023247:AAG_utVTC0rXyfute9xsBdh-IrTUE3432o8")
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "aVim4czsoOzuLxk0CsEsV0JwE58OX90GRD8OvDfT8xH2nfSEC0mMnMCVrwgFcSEi")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET", "rIQ2LLUtYWBcXt5FiMIHuXeeDJqeREbvw8r9NlTJ83gveSAvpSMqd1NBoQjAodC4")
CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "7662080576"))
ENVIRONMENT = "production"

# Sửa đường dẫn file log để phù hợp với cả Windows và Linux
LOG_FILE = os.path.join("logs", "bot_log.json")
PATTERN_LOG_FILE = os.path.join("logs", "pattern_log.txt")
DEBUG_LOG_FILE = os.path.join("logs", "debug.log")
EXCEL_FILE = os.path.join("data", "pivots.xlsx")
BACKUP_DIR = "backup"

# Khởi tạo logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join("logs", "app.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("s1_bot")

# Đảm bảo tệp log tồn tại
for file in [LOG_FILE, PATTERN_LOG_FILE, DEBUG_LOG_FILE]:
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            f.write("=== Log Initialized ===\n")

# Khởi tạo Binance Client
try:
    binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
    # Kiểm tra kết nối
    info = binance_client.get_account()
    logger.info("Binance API connected successfully")
except Exception as e:
    logger.error(f"Binance API connection error: {e}")

def save_log(log_message, filename):
    """Ghi log với timestamp và format nhất quán"""
    try:
        # Thêm timestamp nếu dòng log không phải là dòng trống
        if log_message.strip():
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            formatted_message = f"[{timestamp}] {log_message}"
        else:
            formatted_message = log_message

        with open(filename, "a", encoding="utf-8") as f:
            f.write(formatted_message + "\n")
    except Exception as e:
        logger.error(f"Error saving log: {str(e)}")
        
def set_current_time_and_user(current_time, current_user):
    """Set thời gian hiện tại và user"""
    try:
        # Lấy thời gian hiện tại UTC
        utc_dt = datetime.now(pytz.UTC)
        # Chuyển sang múi giờ Việt Nam
        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        vn_time = utc_dt.astimezone(vn_tz)
        
        # Set time và user
        pivot_data.current_time = vn_time.strftime('%H:%M')  # Chỉ lấy giờ:phút
        pivot_data.user = current_user
        
        # Log thông tin
        save_log("\n=== Cập nhật thông tin phiên ===", DEBUG_LOG_FILE)
        save_log(f"UTC time: {utc_dt.strftime('%Y-%m-%d %H:%M:%S')}", DEBUG_LOG_FILE)
        save_log(f"Vietnam time: {vn_time.strftime('%Y-%m-%d %H:%M:%S (GMT+7)')}", DEBUG_LOG_FILE)
        save_log(f"Pivot time format: {pivot_data.current_time}", DEBUG_LOG_FILE)
        save_log(f"User: {current_user}", DEBUG_LOG_FILE)
        save_log("="*30, DEBUG_LOG_FILE)
        return True

    except Exception as e:
        save_log(f"Error setting time and user: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        return False
                
class PivotData:
    def __init__(self, user="lenhat20791"):
        """
        Khởi tạo S1 bot
        Args:
            user: Tên người dùng
        """
        # Các hằng số
        self.LEFT_BARS = 5          # Số nến so sánh bên trái
        self.RIGHT_BARS = 5         # Số nến so sánh bên phải
        self.MIN_BARS_BETWEEN_PIVOTS = 4  # Khoảng cách tối thiểu giữa các pivot

        # Khởi tạo các biến
        self.price_history = []     # Lưu toàn bộ lịch sử giá
        self.confirmed_pivots = []  # Lưu các pivot đã xác nhận
        self.current_time = None    # Thời gian hiện tại
        self.user = user           # Tên người dùng

        save_log("=== S1 Bot Initialized ===", DEBUG_LOG_FILE)
        save_log(f"👤 User: {self.user}", DEBUG_LOG_FILE)
        save_log(f"⚙️ Settings:", DEBUG_LOG_FILE)
        save_log(f"  - Left bars: {self.LEFT_BARS}", DEBUG_LOG_FILE)
        save_log(f"  - Right bars: {self.RIGHT_BARS}", DEBUG_LOG_FILE)
        save_log(f"  - Min bars between pivots: {self.MIN_BARS_BETWEEN_PIVOTS}", DEBUG_LOG_FILE)
        
    def set_current_time(self, time):
        """Cập nhật current_time"""
        self.current_time = time
        save_log(f"⏰ Đã cập nhật thời gian: {time}", DEBUG_LOG_FILE)    
        
    def clear_all(self):
        """Reset về trạng thái ban đầu"""
        self.price_history.clear()
        self.confirmed_pivots.clear()
        
        save_log("\n=== Reset Toàn Bộ Dữ Liệu ===", DEBUG_LOG_FILE)
        save_log("✅ Đã xóa price history", DEBUG_LOG_FILE)
        save_log("✅ Đã xóa confirmed pivots", DEBUG_LOG_FILE)
        save_log("==============================", DEBUG_LOG_FILE)  
              
    def process_new_data(self, data):
        """
        Xử lý khi có dữ liệu mới - hàm duy nhất để xử lý nến mới
        """
        try:
            # Lấy thời gian hiện tại UTC
            utc_now = datetime.now(pytz.UTC)
            vn_now = utc_now.astimezone(pytz.timezone('Asia/Ho_Chi_Minh'))
            
            # Thêm thông tin thời gian vào data
            data.update({
                'time': utc_now.strftime('%H:%M'),         # Giờ UTC cho pivot
                'utc_date': utc_now.strftime('%Y-%m-%d'),  # Ngày UTC
                'vn_time': vn_now.strftime('%H:%M'),       # Giờ VN
                'vn_date': vn_now.strftime('%Y-%m-%d'),    # Ngày VN
                'vn_datetime': vn_now.strftime('%Y-%m-%d %H:%M')  # Datetime VN đầy đủ
            })
            
            # 1. Thêm nến mới vào lịch sử
            self.price_history.append(data)
            
            # Log thông tin nến mới
            save_log(f"\n=== Nến mới {data['vn_datetime']} ===", DEBUG_LOG_FILE)
            save_log(f"📊 High: ${data['high']:,.2f}, Low: ${data['low']:,.2f}", DEBUG_LOG_FILE)
            save_log(f"📈 Tổng số nến: {len(self.price_history)}", DEBUG_LOG_FILE)
            
            # 2. Nếu không đủ nến cho cửa sổ pivot, thoát
            if len(self.price_history) < (self.LEFT_BARS + self.RIGHT_BARS + 1):
                save_log(f"⚠️ Chưa đủ nến để phát hiện pivot ({len(self.price_history)}/{self.LEFT_BARS + self.RIGHT_BARS + 1})", DEBUG_LOG_FILE)
                return True
            
            # 3. Phát hiện pivot - sử dụng nến ở giữa cửa sổ
            center_idx = len(self.price_history) - self.RIGHT_BARS - 1
            center_candle = self.price_history[center_idx]
            
            # 4. Phân tích cả nến thay vì tách biệt high và low
            high_pivot = self.detect_pivot(center_candle['high'], 'high')
            low_pivot = self.detect_pivot(center_candle['low'], 'low')
            
            # 5. Nếu cả high và low đều là pivot, áp dụng các quy tắc ưu tiên
            if high_pivot and low_pivot:
                # Xác định xu hướng gần đây
                recent_trend = self._determine_recent_trend()
                
                save_log(f"\n⚠️ Cả high và low đều là pivot, xu hướng gần đây: {recent_trend}", DEBUG_LOG_FILE)
                
                if recent_trend == 'bullish':
                    # Ưu tiên pivot high trong xu hướng tăng
                    self._add_confirmed_pivot(high_pivot)
                    save_log(f"✅ Ưu tiên pivot HIGH (${high_pivot['price']:,.2f}) - {high_pivot['type']} trong xu hướng tăng", DEBUG_LOG_FILE)
                else:
                    # Ưu tiên pivot low trong xu hướng giảm
                    self._add_confirmed_pivot(low_pivot)
                    save_log(f"✅ Ưu tiên pivot LOW (${low_pivot['price']:,.2f}) - {low_pivot['type']} trong xu hướng giảm", DEBUG_LOG_FILE)
            else:
                # Xử lý bình thường nếu chỉ một trong hai là pivot
                if high_pivot:
                    self._add_confirmed_pivot(high_pivot)
                if low_pivot:
                    self._add_confirmed_pivot(low_pivot)
                    
            # Cập nhật Excel nếu có pivot mới
            if high_pivot or low_pivot:
                self.save_to_excel()
                
            return True
                
        except Exception as e:
            save_log(f"\n❌ LỖI XỬ LÝ NẾN MỚI:", DEBUG_LOG_FILE)
            save_log(f"- Chi tiết: {str(e)}", DEBUG_LOG_FILE)
            save_log(f"- Trace: {traceback.format_exc()}", DEBUG_LOG_FILE)
            return False

    def _determine_recent_trend(self):
        """Xác định xu hướng gần đây dựa vào các pivot gần nhất"""
        try:
            if len(self.confirmed_pivots) < 4:
                return 'neutral'  # Không đủ dữ liệu
                
            # Lấy 2 pivot high và 2 pivot low gần nhất
            high_pivots = [p for p in self.confirmed_pivots if p['direction'] == 'high']
            low_pivots = [p for p in self.confirmed_pivots if p['direction'] == 'low']
            
            # Sắp xếp theo thời gian (mới nhất đầu tiên)
            high_pivots = sorted(high_pivots, 
                                key=lambda x: datetime.strptime(x["time"], "%H:%M"), 
                                reverse=True)
            low_pivots = sorted(low_pivots, 
                               key=lambda x: datetime.strptime(x["time"], "%H:%M"), 
                               reverse=True)
            
            if len(high_pivots) < 2 or len(low_pivots) < 2:
                return 'neutral'  # Không đủ dữ liệu
                
            # Kiểm tra 2 high gần nhất
            if high_pivots[0]['type'] == 'HH' and high_pivots[1]['type'] == 'HH':
                return 'bullish'  # 2 HH liên tiếp: xu hướng tăng mạnh
                
            # Kiểm tra 2 low gần nhất
            if low_pivots[0]['type'] == 'LL' and low_pivots[1]['type'] == 'LL':
                return 'bearish'  # 2 LL liên tiếp: xu hướng giảm mạnh
                
            # Nếu pivot high gần nhất là HH và pivot low gần nhất là HL
            if (high_pivots and low_pivots and 
                high_pivots[0]['type'] == 'HH' and low_pivots[0]['type'] == 'HL'):
                return 'bullish'  # HH + HL: xu hướng tăng
                
            # Nếu pivot high gần nhất là LH và pivot low gần nhất là LL
            if (high_pivots and low_pivots and 
                high_pivots[0]['type'] == 'LH' and low_pivots[0]['type'] == 'LL'):
                return 'bearish'  # LH + LL: xu hướng giảm
            
            # Trường hợp khác
            return 'neutral'
            
        except Exception as e:
            save_log(f"❌ Lỗi khi xác định xu hướng: {str(e)}", DEBUG_LOG_FILE)
            return 'neutral'  # Default to neutral on error

    def detect_pivot(self, price, direction):
        """
        Phát hiện pivot theo logic TradingView chính xác
        Args:
            price: Giá của điểm pivot tiềm năng
            direction: 'high' hoặc 'low'
        Returns:
            dict: Pivot mới hoặc None
        """
        try:
            save_log(f"\n=== Kiểm tra pivot {direction.upper()} (${price:,.2f}) ===", DEBUG_LOG_FILE)
            
            # 1. Kiểm tra đủ số nến
            if len(self.price_history) < (self.LEFT_BARS + self.RIGHT_BARS + 1):
                save_log(f"⚠️ Chưa đủ nến để xác định pivot", DEBUG_LOG_FILE)
                return None

            # 2. Lấy cửa sổ hiện tại (11 nến)
            window = self.price_history[-(self.LEFT_BARS + self.RIGHT_BARS + 1):]
            center_idx = self.LEFT_BARS
            center_candle = window[center_idx]
            center_time = center_candle['time']
            
            # Khởi tạo biến date với giá trị mặc định
            utc_date = datetime.now(pytz.UTC).strftime('%Y-%m-%d')
            vn_date = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d')
            vn_datetime = None
            utc_datetime = None
            
            # Lấy thông tin ngày giờ chính xác của nến
            if 'vn_datetime' in center_candle:
                # Nếu đã có sẵn vn_datetime
                vn_datetime = center_candle['vn_datetime']
                # Trích xuất date từ vn_datetime
                try:
                    vn_dt = datetime.strptime(vn_datetime, '%Y-%m-%d %H:%M')
                    vn_date = vn_dt.strftime('%Y-%m-%d')
                    utc_dt = vn_dt - timedelta(hours=7)
                    utc_date = utc_dt.strftime('%Y-%m-%d') 
                    utc_time = utc_dt.strftime('%H:%M')
                    utc_datetime = f"{utc_date} {utc_time}"
                except:
                    pass
            else:
                # Xử lý khi không có thông tin thời gian đầy đủ
                save_log(f"⚠️ Không có thông tin thời gian đầy đủ cho nến, sử dụng thời gian UTC mặc định", DEBUG_LOG_FILE)
                utc_time = center_candle.get('time', '')
                utc_datetime = f"{utc_date} {utc_time}"
                
                # Tính thời gian Việt Nam
                try:
                    utc_dt = datetime.strptime(utc_datetime, '%Y-%m-%d %H:%M')
                    vn_dt = utc_dt + timedelta(hours=7)
                    vn_datetime = vn_dt.strftime('%Y-%m-%d %H:%M')
                    vn_date = vn_dt.strftime('%Y-%m-%d')
                except:
                    vn_datetime = f"{vn_date} {center_time}"
            
            # 3. Kiểm tra khoảng cách tối thiểu
            if not self._is_valid_pivot_spacing(center_time):
                save_log(f"❌ Bỏ qua pivot do không đủ khoảng cách tối thiểu {self.MIN_BARS_BETWEEN_PIVOTS} nến", DEBUG_LOG_FILE)
                return None
            
            # 4. So sánh giá với các nến trái và phải
            if direction == "high":
                # So sánh với các nến bên trái
                left_prices = [bar['high'] for bar in window[:center_idx]]
                # So sánh với các nến bên phải
                right_prices = [bar['high'] for bar in window[center_idx + 1:]]
                
                # Log để dễ theo dõi
                save_log(f"High của nến trái: ${max(left_prices):,.2f}", DEBUG_LOG_FILE)
                save_log(f"High của nến phải: ${max(right_prices):,.2f}", DEBUG_LOG_FILE)
                
                # Điều kiện pivot high: cao hơn TẤT CẢ các nến bên trái và bên phải
                is_pivot = price > max(left_prices) and price > max(right_prices)
                
            else:  # direction == "low"
                # So sánh với các nến bên trái
                left_prices = [bar['low'] for bar in window[:center_idx]]
                # So sánh với các nến bên phải
                right_prices = [bar['low'] for bar in window[center_idx + 1:]]
                
                # Log để dễ theo dõi
                save_log(f"Low của nến trái: ${min(left_prices):,.2f}", DEBUG_LOG_FILE)
                save_log(f"Low của nến phải: ${min(right_prices):,.2f}", DEBUG_LOG_FILE)
                
                # Điều kiện pivot low: thấp hơn TẤT CẢ các nến bên trái và bên phải
                is_pivot = price < min(left_prices) and price < min(right_prices)
            
            # 5. Nếu không phải pivot, trả về None
            if not is_pivot:
                save_log(f"❌ Không phải điểm pivot {direction}", DEBUG_LOG_FILE)
                return None
            
            # Log pivot phát hiện với thời gian UTC và GMT+7 (Việt Nam)
            save_log(f"✅ Là điểm pivot {direction} tại {vn_datetime} (UTC: {utc_datetime})", DEBUG_LOG_FILE)
                            
            # 6. Nếu là pivot, tạo đối tượng pivot mới
            new_pivot = {
                'price': float(price),
                'time': center_time,          # Giữ thời gian UTC gốc
                'direction': direction,
                'confirmed': True,
                'utc_date': utc_date,         # Lưu ngày UTC
                'utc_datetime': utc_datetime, # Thêm datetime UTC đầy đủ
                'vn_date': vn_date,           # Lưu ngày Việt Nam
                'vn_datetime': vn_datetime    # Thêm datetime Việt Nam đầy đủ
            }
            
            # 7. Phân loại pivot theo logic TradingView
            pivot_type = self._determine_pivot_type_tv(price, direction)
            if pivot_type:
                new_pivot['type'] = pivot_type
                return new_pivot
            else:
                save_log(f"❌ Không thể phân loại pivot {direction}", DEBUG_LOG_FILE)
                    
            return None
            
        except Exception as e:
            save_log(f"❌ Lỗi khi phát hiện pivot: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            return None

    def _is_valid_pivot_spacing(self, new_pivot_time):
        """Kiểm tra khoảng cách giữa pivot mới và TẤT CẢ pivot đã có"""
        try:
            if not self.confirmed_pivots:
                return True
                
            # Lấy ngày hiện tại (VN time)
            current_date = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).date()
            new_pivot_dt = datetime.strptime(f"{current_date} {new_pivot_time}", '%Y-%m-%d %H:%M')
            
            # Kiểm tra khoảng cách với TẤT CẢ pivot đã có
            for existing_pivot in self.confirmed_pivots:
                # Bỏ qua nếu pivot đó có flag skip_spacing_check
                if existing_pivot.get('skip_spacing_check', False):
                    continue
                    
                existing_pivot_dt = datetime.strptime(f"{current_date} {existing_pivot['time']}", '%Y-%m-%d %H:%M')
                
                # Tính toán khoảng cách thời gian tuyệt đối
                time_diff = abs((existing_pivot_dt - new_pivot_dt).total_seconds())
                
                # Xử lý trường hợp qua ngày
                if time_diff > 22 * 3600:  # Nếu khoảng cách > 22 giờ
                    time_diff = 24 * 3600 - time_diff  # 24h - time_diff
                
                # Chuyển thành số nến (mỗi nến 30 phút = 1800 giây)
                bars_between = time_diff / 1800
                
                if bars_between < self.MIN_BARS_BETWEEN_PIVOTS:
                    save_log(f"⚠️ Bỏ qua pivot tại {new_pivot_time} do khoảng cách quá gần với {existing_pivot['type']} tại {existing_pivot['time']}", DEBUG_LOG_FILE)
                    save_log(f"Khoảng cách thực tế: {bars_between:.1f} nến (tối thiểu {self.MIN_BARS_BETWEEN_PIVOTS})", DEBUG_LOG_FILE)
                    return False
            
            # Nếu qua được tất cả kiểm tra
            return True
                
        except Exception as e:
            save_log(f"❌ Lỗi khi kiểm tra khoảng cách pivot: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            return False

    def _determine_pivot_type_tv(self, price, direction):
        """
        Xác định loại pivot theo logic TradingView
        Args:
            price: Giá của pivot hiện tại
            direction: 'high' hoặc 'low'
        Returns:
            str: Loại pivot (HH, HL, LH, LL) hoặc None
        """
        try:
            # 1. Cần ít nhất 4 pivot trước đó để xác định loại
            if len(self.confirmed_pivots) < 4:
                save_log("⚠️ Chưa đủ pivot để phân loại", DEBUG_LOG_FILE)
                return None
                
            # Log thông tin tổng quát trước khi phân tích chi tiết
            save_log(f"\n=== Phân tích pivot {direction.upper()} (giá: ${price:,.2f}) ===", DEBUG_LOG_FILE)
            save_log(f"Tổng số pivot hiện có: {len(self.confirmed_pivots)}", DEBUG_LOG_FILE)
                
            # 2. Tìm các điểm pivot a, b, c, d, e theo cách TradingView
            [b, c, d, e] = self._find_previous_pivots_tv(direction)
            a = price
            
            # Kiểm tra có đủ điểm pivot không
            if None in [b, c, d]:
                save_log(f"⚠️ Không đủ pivot để phân loại (b={b}, c={c}, d={d})", DEBUG_LOG_FILE)
                return None
            
            save_log(f"\nGiá các pivot dùng để phân loại:", DEBUG_LOG_FILE)
            save_log(f"a = ${a:,.2f} (pivot hiện tại - {direction})", DEBUG_LOG_FILE)
            save_log(f"b = ${b:,.2f} (pivot trước theo TradingView)", DEBUG_LOG_FILE)
            save_log(f"c = ${c:,.2f} (pivot thứ hai theo TradingView)", DEBUG_LOG_FILE)
            save_log(f"d = ${d:,.2f} (pivot thứ ba theo TradingView)", DEBUG_LOG_FILE)
            if e is not None:
                save_log(f"e = ${e:,.2f} (pivot thứ tư theo TradingView)", DEBUG_LOG_FILE)
                
            # Lấy thời gian để log
            current_date = datetime.now(pytz.UTC).date()
            center_time = self.price_history[-(self.RIGHT_BARS + 1)]['time']  # Lấy thời gian của nến center
            utc_dt = datetime.strptime(f"{current_date} {center_time}", '%Y-%m-%d %H:%M')
            vn_dt = utc_dt + timedelta(hours=7)
            vn_time = vn_dt.strftime('%H:%M')  # Chỉ lấy giờ:phút
            
            # 3. Logic xác định loại pivot theo TradingView
            result_type = None
            
            if direction == "high":
                # Higher High: a > b và a > c và c > b và c > d
                if a > b and a > c and c > b and c > d:
                    result_type = "HH"
                    save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type}", DEBUG_LOG_FILE)
                    save_log(f"  Lý do: a > b và a > c và c > b và c > d", DEBUG_LOG_FILE)
                    save_log(f"  Chi tiết: ${a:,.2f} > ${b:,.2f} và ${a:,.2f} > ${c:,.2f} và ${c:,.2f} > ${b:,.2f} và ${c:,.2f} > ${d:,.2f}", DEBUG_LOG_FILE)
                
                # Lower High: Một trong hai điều kiện
                # 1) a <= c và b < c và b < d và d < c và d < e
                # 2) a > b và a < c và b > d
                elif ((e is not None and a <= c and b < c and b < d and d < c and d < e) or 
                      (a > b and a < c and b > d)):
                    result_type = "LH"
                    save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type}", DEBUG_LOG_FILE)
                    if a > b and a < c and b > d:
                        save_log(f"  Lý do: a > b và a < c và b > d", DEBUG_LOG_FILE)
                        save_log(f"  Chi tiết: ${a:,.2f} > ${b:,.2f} và ${a:,.2f} < ${c:,.2f} và ${b:,.2f} > ${d:,.2f}", DEBUG_LOG_FILE)
                    else:
                        save_log(f"  Lý do: a <= c và b < c và b < d và d < c và d < e", DEBUG_LOG_FILE)
                    
                else:
                    save_log("⚠️ Không thể phân loại pivot high theo TradingView", DEBUG_LOG_FILE)
                    # Fallback logic đơn giản
                    if a > b:
                        result_type = "HH"
                        save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type} (logic đơn giản)", DEBUG_LOG_FILE)
                        save_log(f"  Lý do: a > b (${a:,.2f} > ${b:,.2f})", DEBUG_LOG_FILE)
                    elif a < b:
                        result_type = "LH"
                        save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type} (logic đơn giản)", DEBUG_LOG_FILE)
                        save_log(f"  Lý do: a < b (${a:,.2f} < ${b:,.2f})", DEBUG_LOG_FILE)
            
            else:  # direction == "low"
                # Lower Low: a < b và a < c và c < b và c < d
                if a < b and a < c and c < b and c < d:
                    result_type = "LL"
                    save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type}", DEBUG_LOG_FILE)
                    save_log(f"  Lý do: a < b và a < c và c < b và c < d", DEBUG_LOG_FILE)
                    save_log(f"  Chi tiết: ${a:,.2f} < ${b:,.2f} và ${a:,.2f} < ${c:,.2f} và ${c:,.2f} < ${b:,.2f} và ${c:,.2f} < ${d:,.2f}", DEBUG_LOG_FILE)
                
                # Higher Low: Một trong hai điều kiện
                # 1) a >= c và b > c và b > d và d > c và d > e
                # 2) a < b và a > c và b < d
                elif ((e is not None and a >= c and b > c and b > d and d > c and d > e) or 
                      (a < b and a > c and b < d)):
                    result_type = "HL"
                    save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type}", DEBUG_LOG_FILE)
                    if a < b and a > c and b < d:
                        save_log(f"  Lý do: a < b và a > c và b < d", DEBUG_LOG_FILE)
                        save_log(f"  Chi tiết: ${a:,.2f} < ${b:,.2f} và ${a:,.2f} > ${c:,.2f} và ${b:,.2f} < ${d:,.2f}", DEBUG_LOG_FILE)
                    else:
                        save_log(f"  Lý do: a >= c và b > c và b > d và d > c và d > e", DEBUG_LOG_FILE)
                
                else:
                    save_log("⚠️ Không thể phân loại pivot low theo TradingView", DEBUG_LOG_FILE)
                    # Fallback logic đơn giản
                    if a < b:
                        result_type = "LL"
                        save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type} (logic đơn giản)", DEBUG_LOG_FILE)
                        save_log(f"  Lý do: a < b (${a:,.2f} < ${b:,.2f})", DEBUG_LOG_FILE)
                    elif a > b:
                        result_type = "HL"
                        save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type} (logic đơn giản)", DEBUG_LOG_FILE)
                        save_log(f"  Lý do: a > b (${a:,.2f} > ${b:,.2f})", DEBUG_LOG_FILE)
                        
            return result_type
            
        except Exception as e:
            save_log(f"❌ Lỗi khi xác định loại pivot: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            return None

    def _find_previous_pivots_tv(self, direction):
        """
        Tìm các pivot points trước đó theo cách TradingView làm
        Args:
            direction: 'high' hoặc 'low'
        Returns:
            list: [b, c, d, e] - các pivot trước đó theo logic TradingView
        """
        try:
            # Sắp xếp tất cả pivot theo thời gian (cũ đến mới)
            sorted_pivots = sorted(
                self.confirmed_pivots,
                key=lambda x: datetime.strptime(x["time"], "%H:%M")
            )
            
            # Log số lượng pivot theo loại
            high_pivots = [p for p in sorted_pivots if p['direction'] == 'high']
            low_pivots = [p for p in sorted_pivots if p['direction'] == 'low']
            
            save_log(f"Số pivot cùng hướng {direction}: {len(high_pivots if direction == 'high' else low_pivots)}", DEBUG_LOG_FILE)
            save_log(f"Số pivot hướng ngược {('low' if direction == 'high' else 'high')}: {len(low_pivots if direction == 'high' else high_pivots)}", DEBUG_LOG_FILE)
            
            # Kiểm tra xem có đủ pivot không
            if not sorted_pivots or len(sorted_pivots) < 4:
                save_log(f"⚠️ Chưa đủ pivot để xác định các điểm so sánh", DEBUG_LOG_FILE)
                return [None, None, None, None]
            
            # Mô phỏng hàm findprevious() trong chỉ báo TradingView
            # Lấy các pivot với thứ tự zigzag: high -> low -> high -> low hoặc low -> high -> low -> high
            
            # Lấy pivot hiện tại (không tính pivot đang xét)
            current_pivot_direction = direction
            
            # Mảng chứa các pivot theo thứ tự zigzag
            zigzag_pivots = []
            
            # Clone mảng để tìm kiếm
            remaining_pivots = sorted_pivots.copy()
            
            # 1. Tìm pivot ngược hướng gần nhất với pivot hiện tại
            opposite_direction = 'low' if direction == 'high' else 'high'
            opposite_pivots = [p for p in reversed(remaining_pivots) if p['direction'] == opposite_direction]
            if opposite_pivots:
                b = opposite_pivots[0]['price']  # Pivot ngược hướng gần nhất
                zigzag_pivots.append(opposite_pivots[0])
            else:
                b = None
            
            # Nếu không tìm thấy pivot đầu tiên, không thể tiếp tục
            if b is None:
                save_log("⚠️ Không tìm thấy pivot ngược hướng đủ gần", DEBUG_LOG_FILE)
                return [None, None, None, None]
                
            # 2. Tìm pivot cùng hướng gần nhất với pivot B
            if zigzag_pivots:
                idx = remaining_pivots.index(zigzag_pivots[0])
                same_pivots = [p for p in reversed(remaining_pivots[:idx]) if p['direction'] == direction]
                if same_pivots:
                    c = same_pivots[0]['price']  # Pivot cùng hướng gần nhất trước B
                    zigzag_pivots.append(same_pivots[0])
                else:
                    c = None
            else:
                c = None
                
            # 3. Tìm pivot ngược hướng gần nhất với pivot C
            if len(zigzag_pivots) >= 2:
                idx = remaining_pivots.index(zigzag_pivots[1])
                opposite_pivots = [p for p in reversed(remaining_pivots[:idx]) if p['direction'] == opposite_direction]
                if opposite_pivots:
                    d = opposite_pivots[0]['price']  # Pivot ngược hướng gần nhất trước C
                    zigzag_pivots.append(opposite_pivots[0])
                else:
                    d = None
            else:
                d = None
                
            # 4. Tìm pivot cùng hướng gần nhất với pivot D
            if len(zigzag_pivots) >= 3:
                idx = remaining_pivots.index(zigzag_pivots[2])
                same_pivots = [p for p in reversed(remaining_pivots[:idx]) if p['direction'] == direction]
                if same_pivots:
                    e = same_pivots[0]['price']  # Pivot cùng hướng gần nhất trước D
                    zigzag_pivots.append(same_pivots[0])
                else:
                    e = None
            else:
                e = None
                
            # Log chi tiết các pivot tìm thấy
            save_log("\nCác pivot theo cấu trúc ZigZag:", DEBUG_LOG_FILE)
            if zigzag_pivots:
                for i, zp in enumerate(zigzag_pivots):
                    save_log(f"Pivot {chr(98+i)}: {zp['direction']} tại giá ${zp['price']:,.2f} ({zp['time']})", DEBUG_LOG_FILE)
            
            return [b, c, d, e]
            
        except Exception as e:
            save_log(f"❌ Lỗi khi tìm pivot points TradingView style: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            return [None, None, None, None]

    def _add_confirmed_pivot(self, pivot):
        """
        Thêm pivot mới vào lịch sử
        Args:
            pivot: Dictionary chứa thông tin pivot
        Returns:
            bool: True nếu thành công, False nếu thất bại
        """
        try:
            # Kiểm tra trùng lặp trước tiên
            for existing_pivot in self.confirmed_pivots:
                # Kiểm tra nếu đã tồn tại pivot có cùng price, time và direction
                if (abs(existing_pivot.get('price', 0) - pivot.get('price', 0)) < 0.01 and
                    existing_pivot.get('time') == pivot.get('time') and
                    existing_pivot.get('direction') == pivot.get('direction')):
                    save_log(f"⚠️ Pivot đã tồn tại: {pivot.get('type', 'unknown')} tại ${pivot['price']:,.2f} ({pivot.get('vn_datetime', pivot['time'])})", DEBUG_LOG_FILE)
                    return False
            
            # Kiểm tra khoảng cách với tất cả pivot đã có
            if not pivot.get('skip_spacing_check', False):
                for existing_pivot in self.confirmed_pivots:
                    # Bỏ qua pivot có flag skip_spacing_check
                    if existing_pivot.get('skip_spacing_check', False):
                        continue
                        
                    pivot_time_obj = datetime.strptime(pivot['time'], '%H:%M')
                    existing_time_obj = datetime.strptime(existing_pivot['time'], '%H:%M')
                    
                    # Tính khoảng cách theo phút
                    time_diff_minutes = abs((pivot_time_obj.hour - existing_time_obj.hour) * 60 + 
                                          pivot_time_obj.minute - existing_time_obj.minute)
                    
                    # Khoảng cách theo số nến (mỗi nến 30 phút)
                    bars_between = time_diff_minutes / 30
                    
                    # Xử lý trường hợp qua ngày
                    if bars_between > 22:
                        bars_between = 48 - (time_diff_minutes / 30)
                        
                    if bars_between < self.MIN_BARS_BETWEEN_PIVOTS:
                        save_log(f"⚠️ Bỏ qua pivot {pivot.get('type', 'unknown')} tại {pivot['time']} do gần với {existing_pivot.get('type', 'unknown')} ({existing_pivot['time']})", DEBUG_LOG_FILE)
                        save_log(f"Khoảng cách: {bars_between:.1f} nến (tối thiểu {self.MIN_BARS_BETWEEN_PIVOTS})", DEBUG_LOG_FILE)
                        return False
            
            # Đảm bảo pivot có đủ thông tin thời gian Việt Nam
            if 'vn_datetime' not in pivot:
                # Thêm thông tin ngày trước khi lưu pivot
                vn_date = pivot.get('date', datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d'))
                vn_time = pivot.get('time', '')
                pivot['vn_datetime'] = f"{vn_date} {vn_time}"
            
            # Thêm vào danh sách pivot (chỉ thêm một lần)
            self.confirmed_pivots.append(pivot)
            
            save_log("\n=== Thêm Pivot Mới ===", DEBUG_LOG_FILE)
            save_log(f"Loại: {pivot.get('type', 'unknown')}", DEBUG_LOG_FILE)
            save_log(f"Giá: ${pivot['price']:,.2f}", DEBUG_LOG_FILE)
            save_log(f"Thời gian: {pivot.get('vn_datetime', pivot['time'])}", DEBUG_LOG_FILE)
            save_log(f"Hướng: {pivot['direction']}", DEBUG_LOG_FILE)
            
            # Gửi thông báo Telegram khi phát hiện pivot mới
            try:
                bot = Bot(TOKEN)
                
                pivot_type = pivot.get('type', 'Unknown')
                price = pivot['price']
                time_str = pivot.get('vn_datetime', pivot.get('time', 'Unknown time'))
                
                emoji = {
                    'HH': '🚀', 'HL': '🔄', 'LH': '🔄', 'LL': '📉'
                }.get(pivot_type, '🔔')
                
                # Đảm bảo hiển thị đầy đủ giờ:phút
                vn_time = pivot.get('vn_time', '')
                vn_date = pivot.get('vn_date', '')
                time_display = f"{vn_time}" if not vn_date else f"{vn_date} {vn_time}"
                
                message = (
                    f"{emoji} *{pivot_type} Pivot Phát Hiện!*\n\n"
                    f"💰 *Giá:* ${price:,.2f}\n"
                    f"⏰ *Thời gian:* {time_display}\n"
                    f"📊 *Loại:* {pivot_type} ({pivot['direction']})\n"
                )
                
                bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    parse_mode='Markdown'
                )
                
            except Exception as e:
                save_log(f"❌ Lỗi khi gửi thông báo Telegram: {str(e)}", DEBUG_LOG_FILE)
            
            return True
            
        except Exception as e:
            save_log(f"❌ Lỗi khi thêm pivot: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            return False
    
    def get_recent_pivots(self, count=4):
        """Lấy các pivot gần nhất"""
        try:
            save_log("\n=== Lấy pivot gần nhất ===", DEBUG_LOG_FILE)
            save_log(f"Yêu cầu: {count} pivot", DEBUG_LOG_FILE)
            save_log(f"Tổng số pivot hiện có: {len(self.confirmed_pivots)}", DEBUG_LOG_FILE)
            
            recent = self.confirmed_pivots[-count:] if self.confirmed_pivots else []
            
            if recent:
                save_log("Các pivot được chọn:", DEBUG_LOG_FILE)
                for i, p in enumerate(recent, 1):
                    save_log(f"{i}. {p['type']} tại ${p['price']:,.2f} ({p['time']})", DEBUG_LOG_FILE)
            else:
                save_log("Không có pivot nào", DEBUG_LOG_FILE)
            
            return recent

        except Exception as e:
            save_log(f"\n❌ Lỗi khi lấy recent pivots: {str(e)}", DEBUG_LOG_FILE)
            return []
              
    def save_to_excel(self):
        try:
            if not self.confirmed_pivots:
                save_log("\n❌ Không có dữ liệu pivot để lưu", DEBUG_LOG_FILE)
                return

            save_log("\n=== Bắt đầu lưu dữ liệu vào Excel ===", DEBUG_LOG_FILE)
            save_log(f"📊 Tổng số pivot: {len(self.confirmed_pivots)}", DEBUG_LOG_FILE)

            # Lấy pivots đã được sắp xếp đúng thứ tự theo thời gian đầy đủ
            sorted_pivots = self.get_all_pivots()
            
            # Chuẩn bị dữ liệu cho Excel
            excel_data = []
            
            for pivot in sorted_pivots:
                # Ưu tiên sử dụng thông tin datetime đã có sẵn trong pivot
                if 'utc_datetime' in pivot and 'vn_datetime' in pivot:
                    # Đã có cả thông tin UTC và VN datetime
                    try:
                        utc_dt = datetime.strptime(pivot['utc_datetime'], '%Y-%m-%d %H:%M')
                        vn_dt = datetime.strptime(pivot['vn_datetime'], '%Y-%m-%d %H:%M')
                    except Exception as dt_error:
                        save_log(f"Lỗi parse datetime: {str(dt_error)}", DEBUG_LOG_FILE)
                        # Fallback nếu không parse được datetime
                        try:
                            utc_time = pivot['time']
                            utc_date = pivot.get('utc_date', datetime.now(pytz.UTC).strftime('%Y-%m-%d'))
                            utc_dt = datetime.strptime(f"{utc_date} {utc_time}", '%Y-%m-%d %H:%M')
                            vn_dt = utc_dt + timedelta(hours=7)
                        except:
                            # Nếu vẫn lỗi thì dùng thời gian hiện tại
                            utc_dt = datetime.now(pytz.UTC)
                            vn_dt = utc_dt + timedelta(hours=7)
                elif 'utc_date' in pivot:
                    # Có utc_date và time
                    utc_time = pivot['time']
                    utc_date = pivot['utc_date']
                    try:
                        utc_dt = datetime.strptime(f"{utc_date} {utc_time}", '%Y-%m-%d %H:%M')
                        
                        # Kiểm tra nếu có vn_date riêng
                        if 'vn_date' in pivot and 'vn_time' in pivot:
                            vn_date = pivot['vn_date'] 
                            vn_time = pivot['vn_time']
                            vn_dt = datetime.strptime(f"{vn_date} {vn_time}", '%Y-%m-%d %H:%M')
                        else:
                            # Chuyển UTC sang VN
                            vn_dt = utc_dt + timedelta(hours=7)
                    except:
                        # Nếu parse thất bại, sử dụng ngày hiện tại
                        utc_dt = datetime.now(pytz.UTC)
                        vn_dt = utc_dt + timedelta(hours=7)
                else:
                    # Không có thông tin ngày, sử dụng ngày hiện tại
                    utc_time = pivot['time']
                    utc_date = datetime.now(pytz.UTC).strftime('%Y-%m-%d')
                    utc_dt = datetime.strptime(f"{utc_date} {utc_time}", '%Y-%m-%d %H:%M')
                    vn_dt = utc_dt + timedelta(hours=7)
                
                excel_data.append({
                    'utc_datetime': utc_dt,
                    'vn_datetime': vn_dt,
                    'price': pivot['price'],
                    'pivot_type': pivot['type'],
                    'direction': pivot['direction'],
                    'utc_time': utc_dt.strftime('%H:%M'),
                    'utc_date': utc_dt.strftime('%Y-%m-%d'),
                    'vn_time': vn_dt.strftime('%H:%M'),
                    'vn_date': vn_dt.strftime('%Y-%m-%d')
                })

                # Tạo DataFrame
                df = pd.DataFrame(excel_data)

                # Ghi vào Excel với định dạng
                with pd.ExcelWriter(EXCEL_FILE, engine='xlsxwriter') as writer:
                    # Chọn và đổi tên cột để hiển thị cả UTC và VN time
                    columns_to_export = {
                        'utc_datetime': 'Datetime (UTC)',
                        'vn_datetime': 'Datetime (VN)',
                        'price': 'Price',
                        'pivot_type': 'Pivot Type',
                        'direction': 'Direction',
                        'utc_time': 'Time (UTC)',
                        'vn_time': 'Time (VN)',
                        'vn_date': 'Date (VN)'
                    }
                    
                    export_df = df[columns_to_export.keys()].copy()
                    export_df.columns = columns_to_export.values()
                    export_df.to_excel(writer, sheet_name='Pivot Analysis', index=False)
                    
                    workbook = writer.book
                    worksheet = writer.sheets['Pivot Analysis']

                    # Định dạng cột
                    datetime_format = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss'})
                    price_format = workbook.add_format({'num_format': '$#,##0.00'})
                    
                    # Áp dụng định dạng
                    worksheet.set_column('A:A', 20, datetime_format)  # UTC datetime
                    worksheet.set_column('B:B', 20, datetime_format)  # VN datetime
                    worksheet.set_column('C:C', 15, price_format)     # price
                    worksheet.set_column('D:D', 10)                   # pivot_type
                    worksheet.set_column('E:E', 10)                   # direction
                    worksheet.set_column('F:F', 10)                   # UTC time
                    worksheet.set_column('G:G', 10)                   # VN time

                    # Thêm thống kê
                    row = len(export_df) + 2
                    worksheet.write(row, 0, 'Thống kê:')
                    worksheet.write(row + 1, 0, 'Tổng số pivot:')
                    worksheet.write(row + 1, 1, len(export_df), price_format)

                    # Phân bố pivot
                    types_count = export_df['Pivot Type'].value_counts()
                    worksheet.write(row + 2, 0, 'Phân bố pivot:')
                    current_row = row + 3
                    for ptype in ['HH', 'HL', 'LH', 'LL']:
                        if ptype in types_count:
                            worksheet.write(current_row, 0, f'{ptype}:')
                            worksheet.write(current_row, 1, types_count[ptype], price_format)
                            current_row += 1
                            
                    # Thêm chú thích về múi giờ
                    worksheet.write(current_row + 1, 0, 'Chú thích:')
                    worksheet.write(current_row + 2, 0, '- UTC: Giờ quốc tế')
                    worksheet.write(current_row + 3, 0, '- VN: Giờ Việt Nam (GMT+7)')

            save_log("✅ Đã lưu thành công vào Excel", DEBUG_LOG_FILE)

        except Exception as e:
            save_log(f"\n❌ Lỗi khi lưu Excel: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        
    def get_all_pivots(self):
        """Lấy tất cả các pivot theo thứ tự thời gian chính xác (bao gồm ngày)"""
        try:
            if not self.confirmed_pivots:
                return []
                
            # Loại bỏ pivot trùng lặp dựa trên time và price
            unique_pivots = []
            seen = set()
            
            for pivot in self.confirmed_pivots:
                # Tạo key duy nhất từ thời gian và giá (làm tròn để tránh sai số nhỏ)
                key = (pivot['time'], round(pivot['price'], 2))
                if key not in seen:
                    seen.add(key)
                    unique_pivots.append(pivot)
                    
            # Tạo datetime đầy đủ cho mỗi pivot để sắp xếp chính xác
            for pivot in unique_pivots:
                # Ưu tiên sử dụng utc_datetime nếu có
                if 'utc_datetime' in pivot:
                    try:
                        pivot['_sort_dt'] = datetime.strptime(pivot['utc_datetime'], '%Y-%m-%d %H:%M')
                    except:
                        # Fallback: kết hợp từ utc_date và time
                        if 'utc_date' in pivot:
                            utc_date = pivot['utc_date']
                        else:
                            utc_date = datetime.now(pytz.UTC).strftime('%Y-%m-%d')
                        pivot['_sort_dt'] = datetime.strptime(f"{utc_date} {pivot['time']}", '%Y-%m-%d %H:%M')
                else:
                    # Không có utc_datetime, tạo từ utc_date và time
                    if 'utc_date' in pivot:
                        utc_date = pivot['utc_date']
                    else:
                        utc_date = datetime.now(pytz.UTC).strftime('%Y-%m-%d')
                    pivot['_sort_dt'] = datetime.strptime(f"{utc_date} {pivot['time']}", '%Y-%m-%d %H:%M')
            
            # Sắp xếp theo datetime đầy đủ
            sorted_pivots = sorted(
                unique_pivots,
                key=lambda x: x['_sort_dt']
            )
            
            # Loại bỏ trường sort tạm thời
            for pivot in sorted_pivots:
                if '_sort_dt' in pivot:
                    del pivot['_sort_dt']
            
            save_log(f"\nTổng số pivot sau khi loại bỏ trùng lặp: {len(sorted_pivots)}", DEBUG_LOG_FILE)
            
            return sorted_pivots
            
        except Exception as e:
            save_log(f"❌ Lỗi khi lấy all pivots: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            return []

# Create global instance
pivot_data = PivotData() 

def backup_pivots(context: CallbackContext = None):
    """Sao lưu dữ liệu pivot định kỳ"""
    try:
        # Lấy thời gian hiện tại
        backup_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Tên file backup
        backup_file = os.path.join(BACKUP_DIR, f"pivots_backup_{backup_time}.json")
        
        # Đảm bảo thư mục backup tồn tại
        Path(BACKUP_DIR).mkdir(exist_ok=True)
        
        # Lấy dữ liệu pivot
        pivots = pivot_data.get_all_pivots()
        
        # Lưu dữ liệu dưới dạng JSON
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump([{
                'price': p['price'],
                'time': p['time'],
                'direction': p['direction'],
                'type': p.get('type', ''),
                'utc_date': p.get('utc_date', ''),
                'vn_date': p.get('vn_date', ''),
                'vn_datetime': p.get('vn_datetime', ''),
                'utc_datetime': p.get('utc_datetime', '')
            } for p in pivots], f, ensure_ascii=False, indent=2)
            
        # Log thông báo
        save_log(f"✅ Đã sao lưu {len(pivots)} pivot vào {backup_file}", DEBUG_LOG_FILE)
        
        # Xóa backup cũ (giữ 7 ngày gần nhất)
        cleanup_old_backups(days=7)
        
        # Thông báo qua Telegram
        try:
            bot = Bot(TOKEN)
            bot.send_message(
                chat_id=CHAT_ID,
                text=f"✅ *S1 BOT BACKUP*\n\nĐã sao lưu {len(pivots)} pivot!\nFile: `{os.path.basename(backup_file)}`\nThời gian: {backup_time}",
                parse_mode='Markdown'
            )
        except Exception as e:
            save_log(f"Không thể gửi thông báo backup: {str(e)}", DEBUG_LOG_FILE)
            
        return True
        
    except Exception as e:
        save_log(f"❌ Lỗi khi sao lưu pivot: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        return False

def cleanup_old_backups(days=7):
    """Xóa các file backup cũ hơn n ngày"""
    try:
        deleted_count = 0
        
        # Đảm bảo thư mục backup tồn tại
        if not os.path.exists(BACKUP_DIR):
            return
            
        now = datetime.now()
        for file in os.listdir(BACKUP_DIR):
            if file.startswith("pivots_backup_"):
                file_path = os.path.join(BACKUP_DIR, file)
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                
                if (now - file_time).days > days:
                    os.remove(file_path)
                    deleted_count += 1
                    save_log(f"Đã xóa file backup cũ: {file}", DEBUG_LOG_FILE)
        
        if deleted_count > 0:
            save_log(f"✅ Đã xóa {deleted_count} file backup cũ hơn {days} ngày", DEBUG_LOG_FILE)
            
    except Exception as e:
        save_log(f"❌ Lỗi khi xóa file backup cũ: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        

def detect_pivot(price, direction):
    return pivot_data.detect_pivot(price, direction)
    
def get_binance_price(context: CallbackContext):
    try:
        klines = binance_client.futures_klines(symbol="BTCUSDT", interval="30m", limit=2)
        last_candle = klines[-2]  # Ensure we get the closed candle
        high_price = float(last_candle[2])
        low_price = float(last_candle[3])
        close_price = float(last_candle[4])
        
        # Lấy thời gian hiện tại UTC
        now_utc = datetime.now(pytz.UTC)
        # Chuyển sang múi giờ Việt Nam
        now_vn = now_utc.astimezone(pytz.timezone('Asia/Ho_Chi_Minh'))
        
        price_data = {
            "high": high_price,
            "low": low_price,
            "price": close_price,
            "time": now_utc.strftime("%H:%M"),  # Thời gian UTC
            "vn_time": now_vn.strftime("%H:%M"),  # Thời gian Việt Nam
            "utc_date": now_utc.strftime('%Y-%m-%d'),
            "vn_date": now_vn.strftime('%Y-%m-%d'),
            "vn_datetime": now_vn.strftime('%Y-%m-%d %H:%M')
        }
        pivot_data.process_new_data(price_data)
        
        save_log(f"Thu thập dữ liệu nến 30m: High=${high_price:,.2f}, Low=${low_price:,.2f}", DEBUG_LOG_FILE)
        
    except Exception as e:
        logger.error(f"Binance API Error: {e}")
        save_log(f"Binance API Error: {e}", DEBUG_LOG_FILE)
        
def schedule_next_run(job_queue):
    try:
        # Lấy thời gian hiện tại UTC
        now_utc = datetime.now(pytz.UTC)
        # Chuyển sang múi giờ Việt Nam
        now_vn = now_utc.astimezone(pytz.timezone('Asia/Ho_Chi_Minh'))
        
        # Schedule price check mỗi 30 phút
        next_price_run = now_vn.replace(second=0, microsecond=0) + timedelta(minutes=(30 - now_vn.minute % 30))
        price_delay = (next_price_run - now_vn).total_seconds()
        
        save_log(f"Lên lịch price check vào {next_price_run.strftime('%Y-%m-%d %H:%M:%S')} (GMT+7)", DEBUG_LOG_FILE)
        job_queue.run_repeating(get_binance_price, interval=1800, first=price_delay)

        # Schedule auto backup mỗi 6 giờ (21600 giây)
        next_backup = now_vn.replace(minute=0, second=0, microsecond=0) + timedelta(hours=(6 - now_vn.hour % 6))
        backup_delay = (next_backup - now_vn).total_seconds()
        
        save_log(f"Lên lịch backup tự động vào {next_backup.strftime('%Y-%m-%d %H:%M:%S')} (GMT+7)", DEBUG_LOG_FILE)
        job_queue.run_repeating(backup_pivots, interval=21600, first=backup_delay)
        
    except Exception as e:
        logger.error(f"Error scheduling next run: {e}")
        save_log(f"Error scheduling next run: {e}", DEBUG_LOG_FILE)

def help_command(update: Update, context: CallbackContext):
    """Hiển thị trợ giúp cho bot"""
    help_text = (
        "*S1 Bot - Hướng dẫn sử dụng*\n\n"
        "*Các lệnh cơ bản:*\n"
        "/help - Hiển thị trợ giúp này\n"
        "/status - Hiển thị trạng thái của bot\n"
        "/test - Kiểm tra kết nối\n\n"
        
        "*Hoạt động:*\n"
        "- Bot tự động thu thập dữ liệu từ Binance mỗi 30 phút\n"
        "- Khi phát hiện pivot mới, bot sẽ thông báo trong chat này\n"
        "- Backup dữ liệu tự động mỗi 6 giờ\n\n"
        
        "*Chú ý:* Thời gian hiển thị là múi giờ Việt Nam (GMT+7)"
    )
    
    update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN
    )

def status_command(update: Update, context: CallbackContext):
    """Hiển thị trạng thái hiện tại của bot"""
    pivots = pivot_data.get_all_pivots()
    
    # Thông tin chung
    now_utc = datetime.now(pytz.UTC)
    now_vn = now_utc.astimezone(pytz.timezone('Asia/Ho_Chi_Minh'))
    
    # Tạo tin nhắn trạng thái
    status_text = (
        "*S1 Bot Status*\n\n"
        f"⏰ *Thời gian hiện tại:* {now_vn.strftime('%Y-%m-%d %H:%M:%S')} (GMT+7)\n"
        f"🔢 *Tổng số pivot:* {len(pivots)}\n"
        f"👤 *User:* {pivot_data.user}\n"
        f"⚙️ *Environment:* {ENVIRONMENT}\n\n"
    )
    
    # Thêm thông tin về pivot gần đây nhất
    if pivots:
        recent_pivots = pivots[-4:] if len(pivots) >= 4 else pivots
        status_text += "*Pivot gần đây:*\n"
        for pivot in recent_pivots:
            status_text += f"• {pivot['type']}: ${pivot['price']:,.2f} ({pivot.get('vn_datetime', pivot['time'])})\n"
    else:
        status_text += "*Chưa có pivot nào!*\n"
    
    update.message.reply_text(
        status_text,
        parse_mode=ParseMode.MARKDOWN
    )

def test_command(update: Update, context: CallbackContext):
    """Kiểm tra kết nối với Telegram API"""
    update.message.reply_text(
        f"✅ S1 Bot đang kết nối!\n"
        f"⏰ Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"👤 User ID: {update.effective_user.id}"
    )
    
def restore_from_backup():
    """Khôi phục dữ liệu pivot từ file backup gần nhất"""
    try:
        backup_files = [f for f in os.listdir(BACKUP_DIR) if f.startswith("pivots_backup_")]
        
        if not backup_files:
            save_log("⚠️ Không tìm thấy file backup", DEBUG_LOG_FILE)
            return False
            
        # Sắp xếp theo thời gian (mới nhất đầu tiên)
        latest_backup = max(backup_files, key=lambda f: os.path.getctime(os.path.join(BACKUP_DIR, f)))
        backup_path = os.path.join(BACKUP_DIR, latest_backup)
        
        save_log(f"\n=== Khôi phục dữ liệu từ backup ===", DEBUG_LOG_FILE)
        save_log(f"File: {latest_backup}", DEBUG_LOG_FILE)
        
        # Đọc dữ liệu từ file backup
        with open(backup_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
            
        # Clear existing pivots
        pivot_data.clear_all()
        
        # Restore từng pivot
        for pivot in backup_data:
            restored_pivot = {
                'type': pivot.get('type', ''),
                'price': float(pivot['price']),
                'time': pivot['time'],
                'direction': pivot['direction'],
                'confirmed': True,
                'utc_date': pivot.get('utc_date', ''),
                'vn_date': pivot.get('vn_date', ''),
                'vn_datetime': pivot.get('vn_datetime', ''),
                'skip_spacing_check': True  # Để tránh check khoảng cách khi restore
            }
            pivot_data._add_confirmed_pivot(restored_pivot)
            
        save_log(f"✅ Đã khôi phục {len(backup_data)} pivot", DEBUG_LOG_FILE)
        
        # Thông báo qua Telegram
        try:
            bot = Bot(TOKEN)
            bot.send_message(
                chat_id=CHAT_ID,
                text=f"✅ *S1 BOT RESTORE*\n\n"
                    f"Đã khôi phục {len(backup_data)} pivot từ backup!\n"
                    f"File: `{latest_backup}`\n"
                    f"Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode='Markdown'
            )
        except Exception as e:
            save_log(f"Không thể gửi thông báo Telegram: {str(e)}", DEBUG_LOG_FILE)
            
        return True
        
    except Exception as e:
        save_log(f"❌ Lỗi khi khôi phục từ backup: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        return False
        
def main():
    """Main entry point to start the bot."""
    try:
        # Tạo các thư mục cần thiết
        for folder in ["logs", "data", "backup"]:
            Path(folder).mkdir(exist_ok=True)
        
        # Thêm thông tin về thời gian khởi động
        start_time = datetime.now(pytz.UTC)
        start_time_vn = start_time.astimezone(pytz.timezone('Asia/Ho_Chi_Minh'))
        start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        start_time_vn_str = start_time_vn.strftime('%Y-%m-%d %H:%M:%S')
        
        # Khởi tạo S1 Bot
        logger.info("Initializing S1 Bot...")
        save_log("=== S1 Bot khởi động ===", DEBUG_LOG_FILE)
        save_log(f"Môi trường: {ENVIRONMENT}", DEBUG_LOG_FILE)
        save_log(f"Thời gian khởi động UTC: {start_time_str}", DEBUG_LOG_FILE)
        save_log(f"Thời gian khởi động VN: {start_time_vn_str}", DEBUG_LOG_FILE)
        
        # Thiết lập thời gian và user
        current_utc_time = os.environ.get("CURRENT_UTC_TIME", start_time_str)
        current_user = os.environ.get("CURRENT_USER", "lenhat20791")
        set_current_time_and_user(current_utc_time, current_user)
        
       # Thử khôi phục từ backup
        logger.info("Attempting to restore from backup...")
        if restore_from_backup():
            logger.info("Successfully restored from backup")
            save_log("✅ Đã khôi phục dữ liệu từ backup", DEBUG_LOG_FILE)
        else:
            # Nếu không có backup, khởi tạo pivot mặc định
            logger.info("No backup found, initializing default pivots...")
            save_log("🔄 Không có backup, đang khởi tạo pivot mặc định...", DEBUG_LOG_FILE)
            
            # Khởi tạo pivot từ module default_pivots
            if initialize_default_pivots(pivot_data):
                logger.info("Default pivots initialized successfully")
                save_log("✅ Đã khởi tạo pivot mặc định thành công", DEBUG_LOG_FILE)
                # Lưu pivot vào Excel
                pivot_data.save_to_excel()
                # Tạo backup ngay lập tức
                backup_pivots()
            else:
                logger.warning("Failed to initialize default pivots")
                save_log("❌ Không thể khởi tạo pivot mặc định", DEBUG_LOG_FILE)
        
        # Khởi tạo updater
        logger.info("Starting Telegram bot...")
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher
        
        # Thêm các command handlers
        dp.add_handler(CommandHandler('help', help_command))
        dp.add_handler(CommandHandler('status', status_command))
        dp.add_handler(CommandHandler('test', test_command))
        
        # Thiết lập job queue
        job_queue = updater.job_queue
        schedule_next_run(job_queue)
        
        # Gửi thông báo khởi động
        try:
            bot = Bot(TOKEN)
            bot.send_message(
                chat_id=CHAT_ID,
                text=f"🚀 *S1 BOT STARTED*\n\n"
                     f"Bot đã được khởi động thành công!\n"
                     f"Đã khởi tạo {len(pivot_data.confirmed_pivots)} pivot\n"
                     f"Auto backup mỗi 6 giờ\n"
                     f"Môi trường: `{ENVIRONMENT}`\n"
                     f"Thời gian: {start_time_vn_str}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send startup notification: {e}")
            save_log(f"Không thể gửi thông báo khởi động: {str(e)}", DEBUG_LOG_FILE)
        
        # Bắt đầu polling
        logger.info("Bot is now running...")
        save_log("✅ Bot đã bắt đầu chạy", DEBUG_LOG_FILE)
        updater.start_polling(drop_pending_updates=True)
        updater.idle()
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        save_log(f"Lỗi trong hàm main: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)

if __name__ == "__main__":
    main()               
