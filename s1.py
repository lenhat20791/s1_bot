import logging
import json
import pandas as pd
import os
import time
import pytz
import traceback
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext, JobQueue
from binance.client import Client
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.axis import DateAxis
from openpyxl.chart.marker import Marker
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# Configurations
TOKEN = "7637023247:AAG_utVTC0rXyfute9xsBdh-IrTUE3432o8"
BINANCE_API_KEY = "aVim4czsoOzuLxk0CsEsV0JwE58OX90GRD8OvDfT8xH2nfSEC0mMnMCVrwgFcSEi"
BINANCE_API_SECRET = "rIQ2LLUtYWBcXt5FiMIHuXeeDJqeREbvw8r9NlTJ83gveSAvpSMqd1NBoQjAodC4"
CHAT_ID = 7662080576
LOG_FILE = "bot_log.json"
PATTERN_LOG_FILE = "pattern_log.txt"
DEBUG_LOG_FILE = "debug_historical_test.log"
EXCEL_FILE = "pivots.xlsx"
    
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
    """Set thời gian và user hiện tại với support múi giờ Việt Nam"""
    try:
        # Chuyển đổi sang múi giờ Việt Nam nếu input là UTC
        if isinstance(current_time, str):
            try:
                # Parse thời gian UTC
                utc_dt = datetime.strptime(current_time, '%Y-%m-%d %H:%M:%S')
                utc_dt = utc_dt.replace(tzinfo=pytz.UTC)
                # Chuyển sang múi giờ Việt Nam
                vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
                vn_time = utc_dt.astimezone(vn_tz)
                # Format lại thành string
                pivot_data.current_time = vn_time.strftime('%H:%M')  # Chỉ lấy giờ:phút cho pivot
            except ValueError as e:
                save_log(f"Error parsing time: {str(e)}", DEBUG_LOG_FILE)
                return False

        pivot_data.current_user = current_user
        
        # Log chi tiết hơn
        save_log("\n=== Cập nhật thông tin phiên ===", DEBUG_LOG_FILE)
        save_log(f"UTC time: {current_time}", DEBUG_LOG_FILE)
        if 'vn_time' in locals():
            save_log(f"Vietnam time: {vn_time.strftime('%Y-%m-%d %H:%M:%S (GMT+7)')}", DEBUG_LOG_FILE)
        save_log(f"Pivot time format: {pivot_data.current_time}", DEBUG_LOG_FILE)
        save_log(f"User: {current_user}", DEBUG_LOG_FILE)
        save_log("="*30, DEBUG_LOG_FILE)
        return True

    except Exception as e:
        save_log(f"Error setting time and user: {str(e)}", DEBUG_LOG_FILE)
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
        self.MIN_BARS_BETWEEN_PIVOTS = 3  # Khoảng cách tối thiểu giữa các pivot

        # Khởi tạo các biến
        self.price_history = []     # Lưu toàn bộ lịch sử giá
        self.pivot_history = []     # Lưu tất cả các pivot points
        self.potential_pivots = []  # Danh sách pivot tiềm năng chờ xác nhận
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
    
    def detect_potential_pivot(self, price, direction, time):
        """Phát hiện điểm có khả năng là pivot"""
        try:
            # Kiểm tra đủ nến bên trái
            if len(self.price_history) < self.LEFT_BARS:
                save_log(f"\n⚠️ Chưa đủ nến trái để xét pivot tại {time}", DEBUG_LOG_FILE)
                save_log(f"- Cần: {self.LEFT_BARS} nến", DEBUG_LOG_FILE)
                save_log(f"- Hiện có: {len(self.price_history)} nến", DEBUG_LOG_FILE)
                return None

            # Lấy 5 nến trước
            left_bars = self.price_history[-self.LEFT_BARS:]
            
            # Log phân tích
            save_log(f"\n=== Xét điểm tiềm năng {time} ===", DEBUG_LOG_FILE)
            save_log(f"💲 Giá: ${price:,.2f}", DEBUG_LOG_FILE)
            save_log(f"📊 Loại: {'High' if direction == 'high' else 'Low'}", DEBUG_LOG_FILE)
            
            # Kiểm tra với nến trái
            if direction == "high":
                is_potential = price > max(bar['high'] for bar in left_bars)
                if is_potential:
                    save_log("✅ Cao hơn tất cả high của 5 nến trước", DEBUG_LOG_FILE)
                else:
                    save_log("❌ Không cao hơn tất cả high của 5 nến trước", DEBUG_LOG_FILE)
            else:
                is_potential = price < min(bar['low'] for bar in left_bars)
                if is_potential:
                    save_log("✅ Thấp hơn tất cả low của 5 nến trước", DEBUG_LOG_FILE)
                else:
                    save_log("❌ Không thấp hơn tất cả low của 5 nến trước", DEBUG_LOG_FILE)

            if is_potential:
                potential_pivot = {
                    'time': time,
                    'price': price,
                    'direction': direction,
                    'confirmed': False,
                    'right_bars': []  # Sẽ thêm nến phải vào đây
                }
                self.potential_pivots.append(potential_pivot)
                save_log("➡️ Đã thêm vào danh sách chờ xác nhận", DEBUG_LOG_FILE)
                return potential_pivot

            return None

        except Exception as e:
            save_log(f"❌ Lỗi khi phát hiện pivot tiềm năng: {str(e)}", DEBUG_LOG_FILE)
            return None
    
    def confirm_pivot(self, potential_pivot):
        """Xác nhận pivot khi đủ nến phải"""
        try:
            # Kiểm tra số nến phải
            if len(potential_pivot['right_bars']) < self.RIGHT_BARS:
                save_log(f"\n⏳ Pivot {potential_pivot['time']} đang chờ đủ nến phải:", DEBUG_LOG_FILE)
                save_log(f"- Cần: {self.RIGHT_BARS} nến", DEBUG_LOG_FILE)
                save_log(f"- Hiện có: {len(potential_pivot['right_bars'])} nến", DEBUG_LOG_FILE)
                return False

            # So sánh với nến phải
            if potential_pivot['direction'] == 'high':
                is_confirmed = potential_pivot['price'] > max(bar['high'] for bar in potential_pivot['right_bars'])
                comparison = "cao hơn"
            else:
                is_confirmed = potential_pivot['price'] < min(bar['low'] for bar in potential_pivot['right_bars'])
                comparison = "thấp hơn"

            save_log(f"\n🔍 Xác nhận pivot {potential_pivot['time']}:", DEBUG_LOG_FILE)
            if is_confirmed:
                save_log(f"✅ {comparison} tất cả nến phải", DEBUG_LOG_FILE)
                return True
            else:
                save_log(f"❌ Không {comparison} tất cả nến phải", DEBUG_LOG_FILE)
                return False

        except Exception as e:
            save_log(f"❌ Lỗi khi xác nhận pivot: {str(e)}", DEBUG_LOG_FILE)
            return False
    
    def process_new_candle(self, candle_data):
        """
        Xử lý khi có nến mới
        - Thêm vào price history
        - Phát hiện pivot
        """
        try:
            # 1. Thêm nến mới vào lịch sử
            self.price_history.append(candle_data)
            save_log(f"\n=== Nến Mới {candle_data['time']} ===", DEBUG_LOG_FILE)
            save_log(f"📊 High: ${candle_data['high']:,.2f}, Low: ${candle_data['low']:,.2f}", DEBUG_LOG_FILE)
            
            # 2. Nếu không đủ nến cho cửa sổ pivot, thoát
            if len(self.price_history) < (self.LEFT_BARS + self.RIGHT_BARS + 1):
                save_log(f"⚠️ Chưa đủ nến để phát hiện pivot ({len(self.price_history)}/{self.LEFT_BARS + self.RIGHT_BARS + 1})", DEBUG_LOG_FILE)
                return
            
            # 3. Phát hiện pivot - sử dụng nến ở giữa cửa sổ
            center_idx = len(self.price_history) - self.RIGHT_BARS - 1
            center_candle = self.price_history[center_idx]
            
            # 4. Kiểm tra high và low của nến ở giữa cửa sổ
            high_pivot = self.detect_pivot(center_candle['high'], 'high')
            low_pivot = self.detect_pivot(center_candle['low'], 'low')
            
            # 5. Log kết quả
            if high_pivot:
                save_log(f"✅ Phát hiện {high_pivot['type']} tại ${high_pivot['price']:,.2f} ({high_pivot['time']})", DEBUG_LOG_FILE)
                
            if low_pivot:
                save_log(f"✅ Phát hiện {low_pivot['type']} tại ${low_pivot['price']:,.2f} ({low_pivot['time']})", DEBUG_LOG_FILE)
                
            # 6. Cập nhật Excel nếu phát hiện pivot mới
            if high_pivot or low_pivot:
                self.save_to_excel()
                
        except Exception as e:
            save_log(f"\n❌ LỖI XỬ LÝ NẾN MỚI:", DEBUG_LOG_FILE)
            save_log(f"- Chi tiết: {str(e)}", DEBUG_LOG_FILE)
            save_log(f"- Trace: {traceback.format_exc()}", DEBUG_LOG_FILE)
    
    def add_price_data(self, data):
        """
        Thêm dữ liệu giá mới và phân tích pivot
        Args:
            data: Dictionary chứa thông tin nến (time, open, high, low, close)
        Returns:
            bool: True nếu thành công, False nếu thất bại
        """
        try:
            # 1. Cập nhật thông tin
            self.current_time = data["time"]
            save_log(f"\n=== Nến Mới ===", DEBUG_LOG_FILE)
            save_log(f"⏰ Thời điểm: {self.current_time}", DEBUG_LOG_FILE)
            save_log(f"📊 High: ${data['high']:,.2f}, Low: ${data['low']:,.2f}", DEBUG_LOG_FILE)

            # 2. Thêm vào lịch sử
            self.price_history.append(data)
            save_log(f"📈 Tổng số nến: {len(self.price_history)}", DEBUG_LOG_FILE)

            # 3. Phân tích pivot
            high_pivot = self.detect_pivot(data["high"], "high")
            low_pivot = self.detect_pivot(data["low"], "low")

            # 4. Lưu nếu phát hiện pivot mới
            if high_pivot or low_pivot:
                self.save_to_excel()

            return True

        except Exception as e:
            save_log(f"❌ Lỗi khi thêm price data: {str(e)}", DEBUG_LOG_FILE)
            return False
    
    def process_new_data(self, data):
        """Xử lý dữ liệu mới và phát hiện pivot"""
        try:
            # Thêm dữ liệu
            if not self.add_price_data(data):
                return False
                
            # Phát hiện pivot
            high_pivot = self.detect_pivot(data["high"], "high")
            low_pivot = self.detect_pivot(data["low"], "low")

            # Cập nhật Excel nếu cần
            if high_pivot or low_pivot:
                self.save_to_excel()

            return True
            
        except Exception as e:
            save_log(f"❌ Lỗi khi xử lý dữ liệu mới: {str(e)}", DEBUG_LOG_FILE)
            return False    
            
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
            # 1. Kiểm tra đủ số nến
            if len(self.price_history) < (self.LEFT_BARS + self.RIGHT_BARS + 1):
                save_log(f"\n⚠️ Chưa đủ nến để xác định pivot", DEBUG_LOG_FILE)
                return None

            # 2. Lấy cửa sổ hiện tại (11 nến)
            window = self.price_history[-(self.LEFT_BARS + self.RIGHT_BARS + 1):]
            center_idx = self.LEFT_BARS
            center_candle = window[center_idx]
            center_time = center_candle['time']
            
            # 3. So sánh giá với các nến trái và phải
            if direction == "high":
                # So sánh với các nến bên trái
                left_prices = [bar['high'] for bar in window[:center_idx]]
                # So sánh với các nến bên phải
                right_prices = [bar['high'] for bar in window[center_idx + 1:]]
                
                # Điều kiện pivot high: cao hơn TẤT CẢ các nến bên trái và bên phải
                is_pivot = price > max(left_prices) and price > max(right_prices)
                
            else:  # direction == "low"
                # So sánh với các nến bên trái
                left_prices = [bar['low'] for bar in window[:center_idx]]
                # So sánh với các nến bên phải
                right_prices = [bar['low'] for bar in window[center_idx + 1:]]
                
                # Điều kiện pivot low: thấp hơn TẤT CẢ các nến bên trái và bên phải
                is_pivot = price < min(left_prices) and price < min(right_prices)
            
            # 4. Nếu không phải pivot, trả về None
            if not is_pivot:
                return None
            
            # 5. Nếu là pivot, tạo đối tượng pivot mới
            new_pivot = {
                'price': float(price),
                'time': center_time,
                'direction': direction,
                'confirmed': True
            }
            
            # 6. Phân loại pivot
            pivot_type = self._determine_pivot_type(price, direction)
            if pivot_type:
                new_pivot['type'] = pivot_type
                # 7. Thêm vào danh sách pivot xác nhận
                if self._add_confirmed_pivot(new_pivot):
                    return new_pivot
                    
            return None
            
        except Exception as e:
            save_log(f"❌ Lỗi khi phát hiện pivot: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
            return None

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
    
    def _add_confirmed_pivot(self, pivot):
        """
        Thêm pivot mới vào lịch sử
        Args:
            pivot: Dictionary chứa thông tin pivot
        Returns:
            bool: True nếu thành công, False nếu thất bại
        """
        try:
            # Thêm vào cả hai danh sách
            self.pivot_history.append(pivot)
            self.confirmed_pivots.append(pivot)
            
            save_log("\n=== Thêm Pivot Mới ===", DEBUG_LOG_FILE)
            save_log(f"Loại: {pivot['type']}", DEBUG_LOG_FILE)
            save_log(f"Giá: ${pivot['price']:,.2f}", DEBUG_LOG_FILE)
            save_log(f"Thời gian: {pivot['time']}", DEBUG_LOG_FILE)
            
            return True

        except Exception as e:
            save_log(f"❌ Lỗi khi thêm pivot: {str(e)}", DEBUG_LOG_FILE)
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
  
    def classify_pivot(self, new_pivot):
        """Phân loại pivot theo logic TradingView"""
        try:
            if len(self.confirmed_pivots) < 5:
                return None  # Cần ít nhất 5 pivot để phân loại

            # Lấy 5 pivot gần nhất (bao gồm pivot mới)
            recent_points = self.confirmed_pivots[-5:]
            if len(recent_points) < 5:
                return None

            # Gán các giá trị theo cách đặt tên trong TradingView
            a = new_pivot['price']  # Pivot hiện tại
            b = recent_points[-2]['price']  # Pivot trước đó
            c = recent_points[-3]['price']  # Pivot trước b
            d = recent_points[-4]['price']  # Pivot trước c
            e = recent_points[-5]['price']  # Pivot trước d

            # Logic phân loại chính xác theo TradingView
            pivot_type = None
            if new_pivot['direction'] == 'high':
                # Kiểm tra Higher High
                if a > b and a > c and c > b and c > d:
                    pivot_type = 'HH'
                # Kiểm tra Lower High
                elif ((a <= c and (b < c and b < d and d < c and d < e)) or 
                      (a > b and a < c and b > d)):
                    pivot_type = 'LH'
            else:  # direction == 'low'
                # Kiểm tra Lower Low
                if a < b and a < c and c < b and c < d:
                    pivot_type = 'LL'
                # Kiểm tra Higher Low
                elif ((a >= c and (b > c and b > d and d > c and d > e)) or 
                      (a < b and a > c and b < d)):
                    pivot_type = 'HL'

            # Nếu xác định được loại, thêm vào confirmed_pivots
            if pivot_type:
                confirmed_pivot = {
                    'type': pivot_type,
                    'price': new_pivot['price'],
                    'time': new_pivot['time'],
                    'direction': new_pivot['direction']  # Thêm direction
                }
                if confirmed_pivot not in self.confirmed_pivots:
                    self.confirmed_pivots.append(confirmed_pivot)
                    save_log(f"\n✅ Xác nhận {pivot_type} tại ${new_pivot['price']:,.2f} ({new_pivot['time']})", DEBUG_LOG_FILE)
                    return confirmed_pivot

            return None

        except Exception as e:
            save_log(f"\n❌ Lỗi khi phân loại pivot: {str(e)}", DEBUG_LOG_FILE)
            return None
            
    def save_to_excel(self):
        try:
            if not self.confirmed_pivots:
                save_log("\n❌ Không có dữ liệu pivot để lưu", DEBUG_LOG_FILE)
                return

            save_log("\n=== Bắt đầu lưu dữ liệu vào Excel ===", DEBUG_LOG_FILE)
            save_log(f"📊 Tổng số pivot: {len(self.confirmed_pivots)}", DEBUG_LOG_FILE)

            # Chuẩn bị dữ liệu
            current_date = datetime.strptime("2025-03-20", "%Y-%m-%d")  # Ngày hiện tại
            excel_data = []
            
            for pivot in self.confirmed_pivots:
                # Xử lý thời gian
                pivot_time = datetime.strptime(pivot['time'], '%H:%M')
                # Nếu giờ của pivot lớn hơn giờ hiện tại, giảm 1 ngày
                if pivot_time.hour > current_date.hour:
                    pivot_date = current_date - timedelta(days=1)
                else:
                    pivot_date = current_date

                full_datetime = datetime.combine(pivot_date.date(), pivot_time.time())

                excel_data.append({
                    'datetime': full_datetime,
                    'price': pivot['price'],
                    'pivot_type': pivot['type']
                })

            # Tạo DataFrame và sắp xếp theo thời gian
            df = pd.DataFrame(excel_data)
            df = df.sort_values('datetime')

            # Ghi vào Excel với định dạng
            with pd.ExcelWriter('test_results.xlsx', engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Pivot Analysis', index=False)
                workbook = writer.book
                worksheet = writer.sheets['Pivot Analysis']

                # Định dạng cột
                datetime_format = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss'})
                price_format = workbook.add_format({'num_format': '$#,##0.00'})
                
                # Áp dụng định dạng
                worksheet.set_column('A:A', 20, datetime_format)  # datetime
                worksheet.set_column('B:B', 15, price_format)     # price
                worksheet.set_column('C:C', 10)                   # pivot_type

                # Thêm thống kê
                row = len(df) + 2
                worksheet.write(row, 0, 'Thống kê:')
                worksheet.write(row + 1, 0, 'Tổng số pivot:')
                worksheet.write(row + 1, 1, len(df))

                # Phân bố pivot
                types_count = df['pivot_type'].value_counts()
                worksheet.write(row + 2, 0, 'Phân bố pivot:')
                current_row = row + 3
                for ptype in ['HH', 'HL', 'LH', 'LL']:
                    if ptype in types_count:
                        worksheet.write(current_row, 0, f'{ptype}:')
                        worksheet.write(current_row, 1, types_count[ptype])
                        current_row += 1

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
        """Lấy tất cả các pivot theo thứ tự thời gian"""
        try:
            if not self.confirmed_pivots:
                return []
                
            # Sắp xếp theo thời gian
            sorted_pivots = sorted(
                self.confirmed_pivots,
                key=lambda x: datetime.strptime(x["time"], "%H:%M")
            )
            
            save_log(f"\nTổng số pivot: {len(sorted_pivots)}", DEBUG_LOG_FILE)
            return sorted_pivots
                
        except Exception as e:
            save_log(f"❌ Lỗi khi lấy all pivots: {str(e)}", DEBUG_LOG_FILE)
            return []    
                
    def _determine_pivot_type(self, price, direction):
        """
        Xác định loại pivot theo logic TradingView chính xác
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
                
            # 2. Lọc và lấy các pivot cùng hướng với pivot hiện tại
            same_direction_pivots = [p for p in self.confirmed_pivots if p['direction'] == direction]
            if len(same_direction_pivots) < 2:
                save_log(f"⚠️ Chưa đủ pivot cùng hướng {direction} để phân loại", DEBUG_LOG_FILE)
                return None
                
            # 3. Lấy pivot gần nhất cùng hướng
            prev_pivot = same_direction_pivots[-1]
            
            # 4. Lọc và lấy các pivot hướng ngược lại
            opposite_direction = 'low' if direction == 'high' else 'high'
            opposite_direction_pivots = [p for p in self.confirmed_pivots if p['direction'] == opposite_direction]
            if len(opposite_direction_pivots) < 2:
                return None
                
            # 5. Lấy 2 pivot gần nhất có hướng ngược lại
            prev_opposite_pivots = opposite_direction_pivots[-2:]
            
            a = price  # Giá pivot hiện tại
            b = prev_pivot['price']  # Giá pivot trước đó cùng hướng
            c = opposite_direction_pivots[-1]['price']  # Pivot gần nhất hướng ngược lại
            d = opposite_direction_pivots[-2]['price']  # Pivot thứ 2 hướng ngược lại
            
            # 6. Logic xác định loại pivot theo TradingView
            if direction == "high":
                # Higher High: a > b và pivots có khuôn mẫu tăng
                if a > b and c > d:
                    return "HH"
                # Lower High: a < b và pivots có khuôn mẫu giảm
                elif a < b:
                    return "LH"
            else:  # direction == "low"
                # Lower Low: a < b và pivots có khuôn mẫu giảm
                if a < b and c < d:
                    return "LL"
                # Higher Low: a > b và pivots có khuôn mẫu tăng
                elif a > b:
                    return "HL"
                    
            return None
            
        except Exception as e:
            save_log(f"❌ Lỗi khi xác định loại pivot: {str(e)}", DEBUG_LOG_FILE)
            return None
    
    def _is_valid_pivot_spacing(self, new_pivot_time):
        """Kiểm tra khoảng cách giữa pivot mới và pivot gần nhất"""
        try:
            if not self.confirmed_pivots:
                return True
                
            last_pivot = self.confirmed_pivots[-1]
            
            # Chuyển đổi chuỗi thời gian thành datetime với đầy đủ thông tin ngày
            last_pivot_dt = datetime.strptime(f"2025-03-14 {last_pivot['time']}", '%Y-%m-%d %H:%M')
            new_pivot_dt = datetime.strptime(f"2025-03-15 {new_pivot_time}", '%Y-%m-%d %H:%M')
            
            # Nếu new_pivot_time < last_pivot_time, nghĩa là đã qua ngày mới
            if new_pivot_dt < last_pivot_dt:
                new_pivot_dt = new_pivot_dt + timedelta(days=1)
            
            # Tính số nến giữa 2 pivot (mỗi nến 30 phút)
            bars_between = (new_pivot_dt - last_pivot_dt).total_seconds() / 1800
            
            is_valid = bars_between >= self.MIN_BARS_BETWEEN_PIVOTS
            if not is_valid:
                save_log(f"⚠️ Bỏ qua pivot tại {new_pivot_time} do khoảng cách quá gần (cần tối thiểu {self.MIN_BARS_BETWEEN_PIVOTS} nến)", DEBUG_LOG_FILE)
                save_log(f"Range của pivot gần nhất ({last_pivot['type']} tại {last_pivot['time']})", DEBUG_LOG_FILE)
                save_log(f"Khoảng cách thực tế: {bars_between:.1f} nến", DEBUG_LOG_FILE)
                
            return is_valid
                
        except Exception as e:
            save_log(f"❌ Lỗi khi kiểm tra khoảng cách pivot: {str(e)}", DEBUG_LOG_FILE)
            return False
    
    def _find_previous_pivots(self, direction, count=4):
        """
        Tìm 4 pivot points gần nhất cùng hướng
        Args:
            direction: 'high' hoặc 'low'
            count: Số pivot cần tìm
        Returns:
            list: Danh sách giá của các pivot
        """
        results = []
        for pivot in reversed(self.pivot_history):
            if pivot['direction'] == direction and len(results) < count:
                results.append(pivot['price'])
        return results + [None] * (count - len(results)) 
    
# Create global instance
pivot_data = PivotData() 

# Export functions

# Cuối file s1.py thêm dòng này
__all__ = ['pivot_data', 'detect_pivot', 'save_log', 'set_current_time_and_user']
    

def detect_pivot(price, direction):
    return pivot_data.detect_pivot(price, direction)
    
def get_binance_price(context: CallbackContext):
    try:
        klines = binance_client.futures_klines(symbol="BTCUSDT", interval="30m", limit=2)
        last_candle = klines[-2]  # Ensure we get the closed candle
        high_price = float(last_candle[2])
        low_price = float(last_candle[3])
        close_price = float(last_candle[4])
        
        price_data = {
            "high": high_price,
            "low": low_price,
            "price": close_price,
            "time": datetime.now().strftime("%H:%M")
        }
        pivot_data.add_price_data(price_data)
        
        save_log(f"Thu thập dữ liệu nến 30m: High=${high_price:,.2f}, Low=${low_price:,.2f}", DEBUG_LOG_FILE)
        
        detect_pivot(high_price, "high")
        detect_pivot(low_price, "low")
        
    except Exception as e:
        logger.error(f"Binance API Error: {e}")
        save_log(f"Binance API Error: {e}", DEBUG_LOG_FILE)
        
def schedule_next_run(job_queue):
    try:
        # lên lịch chạy khi chẵn 30p
        now = datetime.now()
        next_run = now.replace(second=0, microsecond=0) + timedelta(minutes=(30 - now.minute % 30))
        delay = (next_run - now).total_seconds()
        
        save_log(f"Lên lịch chạy vào {next_run.strftime('%Y-%m-%d %H:%M:%S')}", DEBUG_LOG_FILE)
        # Thay đổi interval từ 300 (5 phút) sang 1800 (30 phút)
        job_queue.run_repeating(get_binance_price, interval=1800, first=delay)
    except Exception as e:
        logger.error(f"Error scheduling next run: {e}")
        save_log(f"Error scheduling next run: {e}", DEBUG_LOG_FILE)
     
def main():
    """Main entry point to start the bot."""
    try:
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher
        job_queue = updater.job_queue
        
        schedule_next_run(job_queue)  # Schedule first run
        
        print("Bot is running...")
        logger.info("Bot started successfully.")
        updater.start_polling()
        updater.idle()
    except Exception as e:
        logger.error(f"Error in main: {e}")
        save_log(f"Error in main: {e}", DEBUG_LOG_FILE)

if __name__ == "__main__":
    main()
