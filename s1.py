# S1 - Cập nhật theo logic TradingView
# Thay thế cho file s1.py hiện tại

import logging
import json
import pandas as pd
import os
import time
import pytz
import traceback
import sys
import io
import re
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
from init_pivots import parse_pivot_input, save_initial_pivots

# Define conversation states
WAITING_FOR_PIVOT_LL = 1
WAITING_FOR_PIVOT_LH = 2
WAITING_FOR_PIVOT_HL = 3
WAITING_FOR_PIVOT_HH = 4

# Thiết lập mã hóa UTF-8 cho đầu ra tiêu chuẩn
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
# Đảm bảo biến môi trường PYTHONIOENCODING được thiết lập
os.environ["PYTHONIOENCODING"] = "utf-8"

# Import cấu hình từ config.py
from config import TOKEN, BINANCE_API_KEY, BINANCE_API_SECRET, CHAT_ID
from config import LOG_FILE, PATTERN_LOG_FILE, DEBUG_LOG_FILE, EXCEL_FILE, ENVIRONMENT
    
# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure log files exist
for file in [LOG_FILE, PATTERN_LOG_FILE, DEBUG_LOG_FILE]:
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            f.write("=== Log Initialized ===\n")

# Initialize Binance Client
binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

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
        print(f"Error saving log: {str(e)}")
        
# Thêm hàm để set các giá trị này
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
        pivot_data.user = current_user  # Sửa từ current_user thành user
        
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
            self.analyze_candle(center_candle)
            
            return True
                
        except Exception as e:
            save_log(f"\n❌ LỖI XỬ LÝ NẾN MỚI:", DEBUG_LOG_FILE)
            save_log(f"- Chi tiết: {str(e)}", DEBUG_LOG_FILE)
            save_log(f"- Trace: {traceback.format_exc()}", DEBUG_LOG_FILE)
            return False

    def analyze_candle(self, candle_data):
        """Phân tích cả nến để phát hiện pivot thay vì tách biệt high và low"""
        try:
            high_pivot = self.detect_pivot(candle_data['high'], 'high')
            low_pivot = self.detect_pivot(candle_data['low'], 'low')
            
            # Nếu cả high và low đều là pivot, áp dụng các quy tắc ưu tiên
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
                
        except Exception as e:
            save_log(f"❌ Lỗi khi phân tích nến: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            
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
            if 'test_time' in center_candle:
                # Nếu có test_time (đã là giờ UTC), chuyển sang giờ Việt Nam
                utc_dt = datetime.strptime(center_candle['test_time'], '%Y-%m-%d %H:%M')
                utc_date = utc_dt.strftime('%Y-%m-%d')
                utc_time = utc_dt.strftime('%H:%M')
                utc_datetime = f"{utc_date} {utc_time}"
                
                vn_dt = utc_dt + timedelta(hours=7)
                vn_time = vn_dt.strftime('%H:%M')
                vn_date = vn_dt.strftime('%Y-%m-%d')
                vn_datetime = f"{vn_date} {vn_time}"
            elif 'vn_datetime' in center_candle:
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
                    
            # Kiểm tra xem nến trung tâm có nằm trong khoảng thời gian test hay không
            if hasattr(self, 'test_start_time_vn') and hasattr(self, 'test_end_time_vn'):
                if vn_datetime:
                    try:
                        pivot_dt = datetime.strptime(vn_datetime, '%Y-%m-%d %H:%M')
                        start_dt = datetime.strptime(self.test_start_time_vn, '%Y-%m-%d %H:%M:%S')
                        end_dt = datetime.strptime(self.test_end_time_vn, '%Y-%m-%d %H:%M:%S')
                        
                        if pivot_dt < start_dt:
                            save_log(f"⚠️ Bỏ qua pivot tại {vn_datetime} - nằm trước thời gian bắt đầu test ({self.test_start_time_vn})", DEBUG_LOG_FILE)
                            return None
                        elif pivot_dt > end_dt:
                            save_log(f"⚠️ Bỏ qua pivot tại {vn_datetime} - nằm sau thời gian kết thúc test ({self.test_end_time_vn})", DEBUG_LOG_FILE)
                            return None
                    except Exception as e:
                        save_log(f"⚠️ Lỗi khi kiểm tra thời gian test: {str(e)}", DEBUG_LOG_FILE)
            
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
                    # Fallback logic cũ của S1 nếu không match TradingView
                    if a > b:
                        result_type = "HH"
                        save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type} (logic S1)", DEBUG_LOG_FILE)
                        save_log(f"  Lý do: a > b (${a:,.2f} > ${b:,.2f})", DEBUG_LOG_FILE)
                    elif a < b:
                        result_type = "LH"
                        save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type} (logic S1)", DEBUG_LOG_FILE)
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
                    # Fallback logic cũ của S1 nếu không match TradingView
                    if a < b:
                        result_type = "LL"
                        save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type} (logic S1)", DEBUG_LOG_FILE)
                        save_log(f"  Lý do: a < b (${a:,.2f} < ${b:,.2f})", DEBUG_LOG_FILE)
                    elif a > b:
                        result_type = "HL"
                        save_log(f"✅ Pivot ({vn_time}) được phân loại là: {result_type} (logic S1)", DEBUG_LOG_FILE)
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
            
            # Trong phần cuối hàm, sau khi đã thêm pivot thành công:
            if ENVIRONMENT == 'production' and not pivot.get('skip_notification', False):
                try:
                    bot = Bot(TOKEN)
                    
                    pivot_type = pivot.get('type', 'Unknown')
                    price = pivot['price']
                    # Sử dụng vn_datetime nếu có, nếu không thì dùng time
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
            
            # Log chi tiết datetime của từng pivot để debug
            save_log("\n=== Debug pivot dates ===", DEBUG_LOG_FILE)
            for i, pivot in enumerate(sorted_pivots):
                save_log(f"Pivot #{i+1}: {pivot.get('type', 'unknown')} - ${pivot['price']:,.2f}", DEBUG_LOG_FILE)
                save_log(f"  UTC time: {pivot.get('time', 'unknown')}", DEBUG_LOG_FILE)
                save_log(f"  UTC date: {pivot.get('utc_date', 'unknown')}", DEBUG_LOG_FILE)
                if 'utc_datetime' in pivot:
                    save_log(f"  UTC datetime: {pivot['utc_datetime']}", DEBUG_LOG_FILE)
                if 'vn_datetime' in pivot:
                    save_log(f"  VN datetime: {pivot['vn_datetime']}", DEBUG_LOG_FILE)
            
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
                
                # Log dữ liệu final để kiểm tra
                save_log(f"Excel data for {pivot['type']} (${pivot['price']:,.2f}):", DEBUG_LOG_FILE)
                save_log(f"  - Final UTC: {utc_dt.strftime('%Y-%m-%d %H:%M')}", DEBUG_LOG_FILE)
                save_log(f"  - Final VN:  {vn_dt.strftime('%Y-%m-%d %H:%M')}", DEBUG_LOG_FILE)
                
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
                with pd.ExcelWriter('test_results.xlsx', engine='xlsxwriter') as writer:
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
            
    def _get_pivot_comment(self, pivot_type, price_change):
        """Tạo comment cho pivot dựa trên loại và % thay đổi"""
        comment = f"{pivot_type}: "
        if pivot_type in ['HH', 'HL']:
            comment += "Bullish " if price_change > 0 else "Caution "
        else:  # LH, LL
            comment += "Bearish " if price_change < 0 else "Caution "
        comment += f"({price_change:+.2f}%)"
        return comment
        
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
        
    def _calculate_bars_between(self, time1, time2):
        """Tính số nến giữa hai thời điểm, xử lý cả trường hợp qua ngày"""
        try:
            if time2.hour < time1.hour:
                # Qua ngày mới
                minutes_to_midnight = (24 * 60) - (time1.hour * 60 + time1.minute)
                minutes_from_midnight = time2.hour * 60 + time2.minute
                total_minutes = minutes_to_midnight + minutes_from_midnight
            else:
                # Cùng ngày
                total_minutes = (time2.hour * 60 + time2.minute) - (time1.hour * 60 + time1.minute)
            
            return total_minutes / 30

        except Exception as e:
            save_log(f"❌ Lỗi khi tính số nến giữa hai thời điểm: {str(e)}", DEBUG_LOG_FILE)
            return 0 
            
    def parse_pivot_input(pivot_text):
        """
        Phân tích cú pháp đầu vào để tạo pivot
        """
        try:
            print(f"Parsing pivot input: {pivot_text}")
            parts = pivot_text.strip().split(":")
            
            # Kiểm tra số lượng phần tử tối thiểu
            if len(parts) < 3:
                print("Không đủ thành phần trong input")
                return None
                
            pivot_type = parts[0].upper()  # LL, LH, HL, HH
            price = float(parts[1])
            
            # Xử lý phần thời gian và ngày tháng
            from datetime import datetime
            import pytz
            
            # Lấy ngày hiện tại theo múi giờ VN
            now = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
            default_vn_date = now.strftime('%Y-%m-%d')
            
            # Xử lý định dạng thời gian để đảm bảo có HH:MM
            if len(parts) == 3:  # Định dạng không có ngày: LL:83597:06:30
                time_str = parts[2]
                vn_date = default_vn_date
            else:  # Có ngày: LL:83597:23-03-2025:06:30
                date_part = parts[2]
                time_str = parts[3]
                
                # Xử lý định dạng ngày DD-MM-YYYY hoặc YYYY-MM-DD
                date_parts = date_part.split('-')
                if len(date_parts) == 3:
                    if int(date_parts[2]) > 1000:  # Năm ở vị trí cuối cùng (DD-MM-YYYY)
                        vn_date = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"  # Chuyển thành YYYY-MM-DD
                    else:
                        vn_date = date_part  # Đã là YYYY-MM-DD
                else:
                    vn_date = default_vn_date
            
            # Đảm bảo vn_time có định dạng HH:MM
            if ":" not in time_str:
                # Nếu time_str chỉ chứa giờ không có phút, thêm ":00"
                if len(time_str) <= 2:
                    vn_time = f"{time_str}:00"
                elif len(time_str) == 4:  # Định dạng 0630 -> 06:30
                    vn_time = f"{time_str[:2]}:{time_str[2:]}"
                else:
                    vn_time = f"{time_str}:00"  # Đảm bảo luôn có định dạng HH:MM
            else:
                vn_time = time_str
                
            # Xác định direction dựa vào loại pivot
            if pivot_type in ["HH", "LH"]:
                direction = "high"
            else:  # LL, HL
                direction = "low"
                
            # Trả về pivot đã phân tích
            result = {
                "type": pivot_type,
                "price": price,
                "vn_time": vn_time,  # Đã đảm bảo định dạng HH:MM
                "vn_date": vn_date,  # Đã đảm bảo không null
                "direction": direction,
                "confirmed": True
            }
            
            print(f"Parsed pivot result: {result}")
            return result
            
        except Exception as e:
            print(f"Lỗi trong parse_pivot_input: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None 
            
    def add_initial_pivot(self, pivot_data):
        """
        API an toàn để thêm pivot ban đầu, cũng kiểm tra khoảng cách
        """
        return self._add_confirmed_pivot(pivot_data)
    
    def add_initial_trading_view_pivots(self, pivots):
        """
        Thêm các pivot ban đầu vào hệ thống theo logic TradingView
        Args:
            pivots: List các pivot với format
            {
                'type': 'LL/LH/HL/HH',
                'price': float,
                'vn_time': 'HH:MM',
                'vn_date': 'YYYY-MM-DD',
                'direction': 'high/low',
                'confirmed': True
            }
        Returns:
            bool: True nếu thành công, False nếu thất bại
        """
        try:
            save_log("\n=== Thêm các pivot ban đầu ===", DEBUG_LOG_FILE)
            save_log(f"Thời gian hiện tại UTC: {datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')}", DEBUG_LOG_FILE)
            save_log(f"Thời gian hiện tại VN: {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')}", DEBUG_LOG_FILE)
            save_log(f"Số lượng pivot: {len(pivots)}", DEBUG_LOG_FILE)
            
            # Kiểm tra số lượng pivot
            if len(pivots) != 4:
                save_log("❌ Số lượng pivot phải là 4 (LL, LH, HL, HH)", DEBUG_LOG_FILE)
                return False
                
            # Kiểm tra thứ tự các loại pivot
            pivot_types = [p['type'] for p in pivots]
            expected_types = ['LL', 'LH', 'HL', 'HH']
            
            if pivot_types != expected_types:
                save_log(f"❌ Thứ tự pivot không đúng. Nhận được: {pivot_types}, cần: {expected_types}", DEBUG_LOG_FILE)
                return False
            
            # Reset lại toàn bộ dữ liệu hiện có
            self.clear_all()
            
            for pivot in pivots:
                try:
                    # Log chi tiết input
                    save_log(f"\nXử lý pivot {pivot['type']}:", DEBUG_LOG_FILE)
                    save_log(f"Input data: {json.dumps(pivot, ensure_ascii=False)}", DEBUG_LOG_FILE)
                    
                    # Chuyển đổi thời gian VN sang UTC
                    vn_dt_str = f"{pivot['vn_date']} {pivot['vn_time']}"  # e.g. "2025-03-24 06:30"
                    save_log(f"VN datetime string: {vn_dt_str}", DEBUG_LOG_FILE)
                    
                    try:
                        # Parse datetime string
                        vn_dt = datetime.strptime(vn_dt_str, '%Y-%m-%d %H:%M')
                        # Localize to VN timezone
                        vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
                        vn_dt = vn_tz.localize(vn_dt)
                        # Convert to UTC
                        utc_dt = vn_dt.astimezone(pytz.UTC)
                        
                        save_log(f"Converted UTC time: {utc_dt.strftime('%Y-%m-%d %H:%M')}", DEBUG_LOG_FILE)
                    except ValueError as dt_error:
                        save_log(f"❌ Lỗi định dạng datetime: {str(dt_error)}", DEBUG_LOG_FILE)
                        return False
                    
                    # Tạo pivot mới với đầy đủ thông tin thời gian
                    new_pivot = {
                        'type': pivot['type'],
                        'price': float(pivot['price']),
                        'direction': pivot['direction'],
                        'confirmed': True,
                        'time': utc_dt.strftime('%H:%M'),         # Giờ UTC cho pivot
                        'utc_date': utc_dt.strftime('%Y-%m-%d'),  # Ngày UTC
                        'utc_datetime': utc_dt.strftime('%Y-%m-%d %H:%M'),
                        'vn_date': pivot['vn_date'],              # Giữ nguyên ngày VN gốc
                        'vn_time': pivot['vn_time'],              # Giữ nguyên giờ VN gốc
                        'vn_datetime': vn_dt_str,                 # Datetime VN đầy đủ
                        'skip_spacing_check': True                 # Bỏ qua kiểm tra khoảng cách cho pivot ban đầu
                    }
                    
                    save_log("Prepared pivot data:", DEBUG_LOG_FILE)
                    save_log(json.dumps(new_pivot, ensure_ascii=False, indent=2), DEBUG_LOG_FILE)
                    
                    # Thêm vào danh sách pivot
                    if self._add_confirmed_pivot(new_pivot):
                        save_log("✅ Thêm thành công!", DEBUG_LOG_FILE)
                    else:
                        save_log("❌ Thêm thất bại!", DEBUG_LOG_FILE)
                        raise Exception(f"Không thể thêm pivot {pivot['type']}")
                        
                except Exception as e:
                    save_log(f"❌ Lỗi khi xử lý pivot {pivot['type']}: {str(e)}", DEBUG_LOG_FILE)
                    save_log(traceback.format_exc(), DEBUG_LOG_FILE)
                    return False
                    
            # Ghi log kết quả cuối cùng
            save_log(f"\n✅ Đã thêm thành công {len(self.confirmed_pivots)} pivot ban đầu", DEBUG_LOG_FILE)
            save_log("Chi tiết:", DEBUG_LOG_FILE)
            for p in self.confirmed_pivots:
                save_log(f"• {p['type']}: ${p['price']:,.2f} ({p['vn_datetime']})", DEBUG_LOG_FILE)
                
            return True
            
        except Exception as e:
            save_log(f"❌ Lỗi khi thêm pivot ban đầu: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            return False
        
# Create global instance
pivot_data = PivotData() 

# Export functions

# Cuối file s1.py thêm dòng này
__all__ = ['pivot_data', 'detect_pivot', 'save_log', 'set_current_time_and_user']

def start_setpivots(update: Update, context: CallbackContext):
    """Bắt đầu quá trình thiết lập 4 pivot ban đầu"""
    try:
        save_log("\n=== Nhận lệnh /setpivots ===", DEBUG_LOG_FILE)
        context.user_data['pivots'] = []
        update.message.reply_text(
            "*Thiết lập 4 pivot ban đầu*\n\n"
            "Vui lòng cung cấp thông tin pivot LL đầu tiên theo một trong các định dạng:\n"
            "`LL:giá:thời_gian`\n"
            "`LL:giá:năm-tháng-ngày:thời_gian`\n"
            "`LL:giá:ngày-tháng-năm:thời_gian`\n\n"
            "Ví dụ:\n"
            "• `LL:79894:00:30` (giá $79,894 lúc 00:30 ngày hiện tại)\n"
            "• `LL:79894:2025-03-23:00:30` (năm-tháng-ngày)\n"
            "• `LL:79894:23-03-2025:00:30` (ngày-tháng-năm)\n\n"
            "_Lưu ý: Sử dụng thời gian theo múi giờ Việt Nam (GMT+7)_",
            parse_mode='Markdown'  # Thay thế ParseMode.MARKDOWN bằng 'Markdown'
        )
        save_log("✅ Đã gửi hướng dẫn thiết lập pivot", DEBUG_LOG_FILE)
        return WAITING_FOR_PIVOT_LL
    except ImportError as e:
        save_log(f"❌ Lỗi import module: {str(e)}", DEBUG_LOG_FILE)
        update.message.reply_text(
            "❌ Lỗi trong quá trình khởi tạo lệnh /setpivots. Vui lòng liên hệ admin."
        )
        return ConversationHandler.END
    except Exception as e:
        save_log(f"❌ Lỗi không xác định trong start_setpivots: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        update.message.reply_text(
            "❌ Có lỗi xảy ra. Vui lòng thử lại sau hoặc liên hệ admin."
        )
        return ConversationHandler.END

def process_pivot_ll(update: Update, context: CallbackContext):
    """Xử lý pivot LL"""
    try:
        pivot_text = update.message.text
        save_log(f"Đang xử lý input pivot LL: {pivot_text}", DEBUG_LOG_FILE)
        
        try:
            new_pivot = parse_pivot_input(pivot_text)
            save_log(f"Kết quả parse pivot: {new_pivot}", DEBUG_LOG_FILE)
        except Exception as parse_error:
            save_log(f"❌ Lỗi khi parse pivot: {str(parse_error)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            update.message.reply_text(
                "❌ Có lỗi khi xử lý định dạng pivot. Vui lòng thử lại với định dạng đơn giản hơn.\n"
                "Ví dụ: `LL:83597:06:30`",
                parse_mode='Markdown'
            )
            return WAITING_FOR_PIVOT_LL
        
        if not new_pivot or new_pivot['type'] != 'LL':
            update.message.reply_text(
                "❌ Định dạng không đúng hoặc loại pivot không phải LL!\n"
                "Vui lòng nhập lại theo định dạng: `LL:giá:thời_gian`\n"
                "Ví dụ: `LL:79894:00:30`",
                parse_mode='Markdown'
            )
            return WAITING_FOR_PIVOT_LL
            
        # Lưu pivot vào user_data
        context.user_data['pivots'] = context.user_data.get('pivots', [])
        context.user_data['pivots'].append(new_pivot)
        
        # Hiển thị thời gian CHÍNH XÁC bao gồm cả phút
        date_info = f" ngày {new_pivot['vn_date']}" if 'vn_date' in new_pivot else ""
        
        update.message.reply_text(
            f"✅ Đã lưu pivot LL: ${new_pivot['price']:,.2f} lúc {new_pivot['vn_time']}{date_info}\n\n"
            "Vui lòng cung cấp thông tin pivot LH theo định dạng:\n"
            "`LH:giá:thời_gian`\n\n"
            "Ví dụ: `LH:82266:09:30`",
            parse_mode='Markdown'
        )
        
        return WAITING_FOR_PIVOT_LH
        
    except Exception as e:
        save_log(f"❌ Lỗi trong process_pivot_ll: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        try:
            update.message.reply_text(
                "❌ Có lỗi xảy ra khi xử lý pivot LL. Vui lòng thử lại sau.",
                parse_mode='Markdown'
            )
        except:
            pass
        return WAITING_FOR_PIVOT_LL

def process_pivot_lh(update: Update, context: CallbackContext):
    """Xử lý pivot LH"""
    try:
        pivot_text = update.message.text
        save_log(f"Đang xử lý input pivot LH: {pivot_text}", DEBUG_LOG_FILE)
        
        try:
            new_pivot = parse_pivot_input(pivot_text)
            save_log(f"Kết quả parse pivot: {new_pivot}", DEBUG_LOG_FILE)
        except Exception as parse_error:
            save_log(f"❌ Lỗi khi parse pivot: {str(parse_error)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            update.message.reply_text(
                "❌ Có lỗi khi xử lý định dạng pivot. Vui lòng thử lại với định dạng đơn giản hơn.\n"
                "Ví dụ: `LH:82266:09:30`",
                parse_mode='Markdown'
            )
            return WAITING_FOR_PIVOT_LH
        
        if not new_pivot or new_pivot['type'] != 'LH':
            update.message.reply_text(
                "❌ Định dạng không đúng hoặc loại pivot không phải LH!\n"
                "Vui lòng nhập lại theo định dạng: `LH:giá:thời_gian`\n"
                "Ví dụ: `LH:82266:09:30`",
                parse_mode='Markdown'
            )
            return WAITING_FOR_PIVOT_LH
            
        # Lưu pivot vào user_data
        context.user_data['pivots'].append(new_pivot)
        
        # Hiển thị thời gian CHÍNH XÁC bao gồm cả phút
        date_info = f" ngày {new_pivot['vn_date']}" if 'vn_date' in new_pivot else ""
        
        update.message.reply_text(
            f"✅ Đã lưu pivot LH: ${new_pivot['price']:,.2f} lúc {new_pivot['vn_time']}{date_info}\n\n"
            "Vui lòng cung cấp thông tin pivot HL theo định dạng:\n"
            "`HL:giá:thời_gian`\n\n"
            "Ví dụ: `HL:81730:13:30`",
            parse_mode='Markdown'
        )
        
        return WAITING_FOR_PIVOT_HL
        
    except Exception as e:
        save_log(f"❌ Lỗi trong process_pivot_lh: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        try:
            update.message.reply_text(
                "❌ Có lỗi xảy ra khi xử lý pivot LH. Vui lòng thử lại sau.",
                parse_mode='Markdown'
            )
        except:
            pass
        return WAITING_FOR_PIVOT_LH

def process_pivot_hl(update: Update, context: CallbackContext):
    """Xử lý pivot HL"""
    try:
        pivot_text = update.message.text
        save_log(f"Đang xử lý input pivot HL: {pivot_text}", DEBUG_LOG_FILE)
        
        try:
            new_pivot = parse_pivot_input(pivot_text)
            save_log(f"Kết quả parse pivot: {new_pivot}", DEBUG_LOG_FILE)
        except Exception as parse_error:
            save_log(f"❌ Lỗi khi parse pivot: {str(parse_error)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            update.message.reply_text(
                "❌ Có lỗi khi xử lý định dạng pivot. Vui lòng thử lại với định dạng đơn giản hơn.\n"
                "Ví dụ: `HL:81730:13:30`",
                parse_mode='Markdown'
            )
            return WAITING_FOR_PIVOT_HL
        
        if not new_pivot or new_pivot['type'] != 'HL':
            update.message.reply_text(
                "❌ Định dạng không đúng hoặc loại pivot không phải HL!\n"
                "Vui lòng nhập lại theo định dạng: `HL:giá:thời_gian`\n"
                "Ví dụ: `HL:81730:13:30`",
                parse_mode='Markdown'
            )
            return WAITING_FOR_PIVOT_HL
            
        # Lưu pivot vào user_data
        context.user_data['pivots'].append(new_pivot)
        
        # Hiển thị thời gian CHÍNH XÁC bao gồm cả phút
        date_info = f" ngày {new_pivot['vn_date']}" if 'vn_date' in new_pivot else ""
        
        update.message.reply_text(
            f"✅ Đã lưu pivot HL: ${new_pivot['price']:,.2f} lúc {new_pivot['vn_time']}{date_info}\n\n"
            "Vui lòng cung cấp thông tin pivot HH theo định dạng:\n"
            "`HH:giá:thời_gian`\n\n"
            "Ví dụ: `HH:85270:22:30`",
            parse_mode='Markdown'
        )
        
        return WAITING_FOR_PIVOT_HH
        
    except Exception as e:
        save_log(f"❌ Lỗi trong process_pivot_hl: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        try:
            update.message.reply_text(
                "❌ Có lỗi xảy ra khi xử lý pivot HL. Vui lòng thử lại sau.",
                parse_mode='Markdown'
            )
        except:
            pass
        return WAITING_FOR_PIVOT_HL

def process_pivot_hh(update: Update, context: CallbackContext):
    """Xử lý pivot HH"""
    try:
        pivot_text = update.message.text
        save_log(f"Đang xử lý input pivot HH: {pivot_text}", DEBUG_LOG_FILE)
        
        try:
            new_pivot = parse_pivot_input(pivot_text)
            save_log(f"Kết quả parse pivot: {new_pivot}", DEBUG_LOG_FILE)
        except Exception as parse_error:
            save_log(f"❌ Lỗi khi parse pivot: {str(parse_error)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            update.message.reply_text(
                "❌ Có lỗi khi xử lý định dạng pivot. Vui lòng thử lại với định dạng đơn giản hơn.\n"
                "Ví dụ: `HH:85270:22:30`",
                parse_mode='Markdown'
            )
            return WAITING_FOR_PIVOT_HH
        
        if not new_pivot or new_pivot['type'] != 'HH':
            update.message.reply_text(
                "❌ Định dạng không đúng hoặc loại pivot không phải HH!\n"
                "Vui lòng nhập lại theo định dạng: `HH:giá:thời_gian`\n"
                "Ví dụ: `HH:85270:22:30`",
                parse_mode='Markdown'
            )
            return WAITING_FOR_PIVOT_HH
            
        # Lưu pivot vào user_data
        context.user_data['pivots'].append(new_pivot)
        
        # Lưu tất cả pivot và thêm vào S1
        pivots = context.user_data['pivots']
        
        # Lưu vào file để có thể sử dụng lại sau này
        save_initial_pivots(pivots)
        
        # Thêm pivot vào instance PivotData
        import sys
        current_module = sys.modules[__name__]
        current_module.pivot_data.add_initial_trading_view_pivots(pivots)
        
        # Tạo thông tin pivot với ngày và giờ chính xác
        pivot_info = "\n".join([
            f"• {p['type']}: ${p['price']:,.2f} ({p['vn_time']}" + 
            (f" ngày {p['vn_date']}" if 'vn_date' in p else "") + ")"
            for p in pivots
        ])
        
        update.message.reply_text(
            f"✅ *Đã thiết lập thành công 4 pivot ban đầu!*\n\n"
            f"{pivot_info}\n\n"
            f"S1 Bot đã sẵn sàng phát hiện các pivot mới.",
            parse_mode='Markdown'
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        save_log(f"❌ Lỗi trong process_pivot_hh: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        try:
            update.message.reply_text(
                "❌ Có lỗi xảy ra khi xử lý pivot HH. Vui lòng thử lại sau.",
                parse_mode='Markdown'
            )
        except:
            pass
        return WAITING_FOR_PIVOT_HH

def cancel_setpivots(update: Update, context: CallbackContext):
    """Hủy quá trình thiết lập pivot"""
    update.message.reply_text(
        "❌ Đã hủy quá trình thiết lập pivot ban đầu."
    )
    return ConversationHandler.END
    
def backup_pivots():
    """Sao lưu dữ liệu pivot định kỳ"""
    try:
        # Lấy thời gian hiện tại
        backup_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Tên file backup
        backup_file = f"backup/pivots_backup_{backup_time}.json"
        
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
                'vn_datetime': p.get('vn_datetime', '')
            } for p in pivots], f, ensure_ascii=False, indent=2)
            
        # Log thông báo
        save_log(f"✅ Đã sao lưu {len(pivots)} pivot vào {backup_file}", DEBUG_LOG_FILE)
        
        # Thông báo qua Telegram
        bot = Bot(TOKEN)
        bot.send_message(
            chat_id=CHAT_ID,
            text=f"✅ *S1 BOT BACKUP*\n\nĐã sao lưu {len(pivots)} pivot!\nFile: `{backup_file}`\nThời gian: {backup_time}",
            parse_mode='Markdown'
        )
        
        return True
        
    except Exception as e:
        save_log(f"❌ Lỗi khi sao lưu pivot: {str(e)}", DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        return False
        
def send_error_notification(error_message):
    """Gửi thông báo lỗi qua Telegram"""
    try:
        bot = Bot(TOKEN)
        bot.send_message(
            chat_id=CHAT_ID,
            text=f"⚠️ *S1 BOT ERROR*\n\n{error_message}\n\nThời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode='Markdown'
        )
        return True
    except Exception as e:
        print(f"Không thể gửi thông báo lỗi: {str(e)}")
        save_log(f"Không thể gửi thông báo lỗi: {str(e)}", DEBUG_LOG_FILE)
        return False        
        
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
            "time": now_vn.strftime("%H:%M")  # Sử dụng giờ Việt Nam
        }
        pivot_data.process_new_data(price_data)  # Sử dụng hàm hợp nhất
        
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
        
        # lên lịch chạy khi chẵn 30p
        next_run = now_vn.replace(second=0, microsecond=0) + timedelta(minutes=(30 - now_vn.minute % 30))
        delay = (next_run - now_vn).total_seconds()
        
        save_log(f"Lên lịch chạy vào {next_run.strftime('%Y-%m-%d %H:%M:%S')} (GMT+7)", DEBUG_LOG_FILE)
        # Thay đổi interval từ 300 (5 phút) sang 1800 (30 phút)
        job_queue.run_repeating(get_binance_price, interval=1800, first=delay)
    except Exception as e:
        logger.error(f"Error scheduling next run: {e}")
        save_log(f"Error scheduling next run: {e}", DEBUG_LOG_FILE)
        
def help_command(update: Update, context: CallbackContext):
    """Hiển thị trợ giúp cho bot"""
    help_text = (
        "*S1 Bot - Hướng dẫn sử dụng*\n\n"
        "*Các lệnh cơ bản:*\n"
        "/help - Hiển thị trợ giúp này\n"
        "/setpivots - Thiết lập 4 pivot ban đầu để S1 có thể phân loại pivot mới\n"
        "/status - Hiển thị trạng thái của bot\n\n"
        
        "*Quy trình sử dụng:*\n"
        "1. Dùng lệnh /setpivots để thiết lập 4 pivot ban đầu (LL, LH, HL, HH)\n"
        "2. Bot sẽ tự động thu thập dữ liệu từ Binance mỗi 30 phút\n"
        "3. Khi phát hiện pivot mới, bot sẽ thông báo trong chat này\n\n"
        
        "*Chú ý:* Tất cả thời gian được sử dụng là múi giờ Việt Nam (GMT+7)"
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
        status_text += "*Chưa có pivot nào!* Sử dụng /setpivots để thiết lập 4 pivot ban đầu.\n"
    
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
    
def main():
    """Main entry point to start the bot."""
    try:
        # Thêm thông tin về thời gian khởi động
        start_time = datetime.now()
        start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Kiểm tra các thư mục cần thiết
        for dir_path in ['logs', 'data', 'backup']:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                
        # Thông báo khởi động
        save_log("=== S1 Bot khởi động ===", DEBUG_LOG_FILE)
        save_log(f"Môi trường: {ENVIRONMENT}", DEBUG_LOG_FILE)
        save_log(f"Thời gian khởi động: {start_time_str}", DEBUG_LOG_FILE)
                
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher
        job_queue = updater.job_queue
        
        schedule_next_run(job_queue)  # Schedule first run

        # Set up conversation handler for setting initial pivots
        setpivots_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('setpivots', start_setpivots)],
            states={
                WAITING_FOR_PIVOT_LL: [
                    MessageHandler(Filters.text & ~Filters.command, process_pivot_ll)
                ],
                WAITING_FOR_PIVOT_LH: [
                    MessageHandler(Filters.text & ~Filters.command, process_pivot_lh)
                ],
                WAITING_FOR_PIVOT_HL: [
                    MessageHandler(Filters.text & ~Filters.command, process_pivot_hl)
                ],
                WAITING_FOR_PIVOT_HH: [
                    MessageHandler(Filters.text & ~Filters.command, process_pivot_hh)
                ]
            },
            fallbacks=[CommandHandler('cancel', cancel_setpivots)],
            allow_reentry=True
        )

        # Add handlers to dispatcher
        dp.add_handler(setpivots_conv_handler)
        dp.add_handler(CommandHandler('help', help_command))
        dp.add_handler(CommandHandler('status', status_command))
        dp.add_handler(CommandHandler('test', test_command))
        
        # Thông báo khởi động qua Telegram
        bot = Bot(TOKEN)
        bot.send_message(
            chat_id=CHAT_ID,
            text=f"🚀 *S1 BOT STARTED*\n\nBot đã được khởi động thành công!\nMôi trường: `{ENVIRONMENT}`\nThời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode='Markdown'
        )
        
        print("S1 Bot is running...")  # Thay thế bằng tiếng Anh hoặc không dấu
        logger.info("Bot started successfully.")
        updater.start_polling()
        updater.idle()
    except Exception as e:
        error_msg = f"Lỗi trong hàm main: {str(e)}"
        logger.error(error_msg)
        save_log(error_msg, DEBUG_LOG_FILE)
        save_log(traceback.format_exc(), DEBUG_LOG_FILE)
        send_error_notification(error_msg)

if __name__ == "__main__":
    main()
