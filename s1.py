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
    def __init__(self):
        """Khởi tạo với logic TradingView"""
        # Các thông số cơ bản
        self.LEFT_BARS = 5        # Số nến so sánh bên trái
        self.RIGHT_BARS = 5       # Số nến so sánh bên phải
        self.MIN_BARS_BETWEEN_PIVOTS = 5
        # Lưu trữ dữ liệu
        self.price_history = []   # Lịch sử giá
        self.confirmed_pivots = [] # Các pivot đã xác nhận
        
        # Thời gian hiện tại
        self.current_time = None
        
        save_log("🔄 Khởi tạo PivotData với logic TradingView", DEBUG_LOG_FILE)
        
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
        
    def add_price_data(self, data):
        """Thêm dữ liệu giá mới với logic đơn giản hóa"""
        try:
            # Cập nhật thời gian và log
            self.current_time = data["time"]
            save_log(f"\n⏰ Thời điểm: {self.current_time}", DEBUG_LOG_FILE)
            save_log(f"📊 High: ${data['high']:,.2f}, Low: ${data['low']:,.2f}", DEBUG_LOG_FILE)

            # Thêm vào lịch sử giá
            self.price_history.append(data)
            
            # Giữ số lượng nến cố định
            max_bars = self.LEFT_BARS + self.RIGHT_BARS + 1
            if len(self.price_history) > max_bars:
                self.price_history = self.price_history[-max_bars:]
            
            # Phát hiện pivot
            high_pivot = self.detect_pivot(data["high"], "high")
            low_pivot = self.detect_pivot(data["low"], "low")

            if high_pivot or low_pivot:
                self.save_to_excel()  # Cập nhật Excel khi có pivot mới

            return True

        except Exception as e:
            save_log(f"❌ Lỗi khi thêm price data: {str(e)}", DEBUG_LOG_FILE)
            return False
             
    def detect_pivot(self, price, direction):
        """
        Phát hiện pivot với kiểm tra khoảng cách và xử lý qua ngày mới
        Args:
            price (float): Giá cần kiểm tra
            direction (str): 'high' hoặc 'low'
        Returns:
            dict: Thông tin pivot nếu phát hiện được, None nếu không
        """
        try:
            # 1. Kiểm tra đủ số lượng nến
            if len(self.price_history) < (self.LEFT_BARS + self.RIGHT_BARS + 1):
                save_log(f"⏳ Đang thu thập dữ liệu: {len(self.price_history)}/{self.LEFT_BARS + self.RIGHT_BARS + 1} nến", DEBUG_LOG_FILE)
                return None

            # 2. Xác định nến trung tâm và các nến xung quanh
            center_idx = self.LEFT_BARS
            center_candle = self.price_history[center_idx]
            left_bars = self.price_history[:center_idx]
            right_bars = self.price_history[center_idx + 1:]

            # Log thời gian hiện tại và thời gian của nến đang xét
            current_time_utc = datetime.strptime("2025-03-20 06:05:11", "%Y-%m-%d %H:%M:%S")
            candle_time = datetime.strptime(center_candle['time'], '%H:%M').replace(
                year=current_time_utc.year,
                month=current_time_utc.month,
                day=current_time_utc.day
            )
            
            save_log(f"\n=== Kiểm tra Pivot tại {center_candle['time']} ===", DEBUG_LOG_FILE)
            save_log(f"⏰ Thời điểm hiện tại (UTC): {current_time_utc}", DEBUG_LOG_FILE)
            save_log(f"📊 Giá: ${price:,.2f}", DEBUG_LOG_FILE)
            save_log(f"📍 Loại: {direction}", DEBUG_LOG_FILE)

            # 3. Kiểm tra điều kiện cơ bản của pivot
            if direction == "high":
                is_pivot = all(center_candle['high'] > bar['high'] for bar in left_bars) and \
                          all(center_candle['high'] > bar['high'] for bar in right_bars)
                pivot_price = center_candle['high']
            else:
                is_pivot = all(center_candle['low'] < bar['low'] for bar in left_bars) and \
                          all(center_candle['low'] < bar['low'] for bar in right_bars)
                pivot_price = center_candle['low']

            if not is_pivot:
                save_log("❌ Không thỏa mãn điều kiện pivot", DEBUG_LOG_FILE)
                return None

            # 4. Kiểm tra khoảng cách với pivot gần nhất
            if self.confirmed_pivots:
                last_pivot = self.confirmed_pivots[-1]
                last_pivot_time = datetime.strptime(last_pivot['time'], '%H:%M').replace(
                    year=current_time_utc.year,
                    month=current_time_utc.month,
                    day=current_time_utc.day
                )

                # Xử lý qua ngày mới
                if candle_time.hour < last_pivot_time.hour:
                    save_log(f"📅 Phát hiện qua ngày mới", DEBUG_LOG_FILE)
                    save_log(f"🔄 Reset danh sách pivot nhưng giữ pivot cuối {last_pivot['time']} làm tham chiếu", DEBUG_LOG_FILE)
                    reference_pivot = last_pivot.copy()
                    reference_pivot['is_reference'] = True  # Đánh dấu là pivot tham chiếu
                    self.confirmed_pivots = [reference_pivot]
                    last_pivot_time = last_pivot_time - timedelta(days=1)  # Giảm 1 ngày để tính khoảng cách

                # Tính khoảng cách giữa các pivot
                bars_between = self._calculate_bars_between(last_pivot_time, candle_time)
                
                save_log(f"⏱️ Khoảng cách: {bars_between:.1f} nến", DEBUG_LOG_FILE)
                save_log(f"📊 Yêu cầu tối thiểu: {self.MIN_BARS_BETWEEN_PIVOTS} nến", DEBUG_LOG_FILE)

                if bars_between < self.MIN_BARS_BETWEEN_PIVOTS:
                    save_log(f"⚠️ Bỏ qua do khoảng cách quá gần", DEBUG_LOG_FILE)
                    return None
                    
                save_log(f"✅ Đủ khoảng cách", DEBUG_LOG_FILE)

            # 5. Xác định loại pivot
            pivot_type = self._determine_pivot_type(pivot_price, direction)
            if not pivot_type:
                return None

            # 6. Tạo và thêm pivot mới
            new_pivot = {
                'type': pivot_type,
                'price': float(pivot_price),
                'time': center_candle['time'],
                'direction': direction,
                'created_at': current_time_utc.strftime('%Y-%m-%d %H:%M:%S')
            }

            if self._add_confirmed_pivot(new_pivot):
                save_log(f"✅ Phát hiện pivot {pivot_type} tại ${pivot_price:,.2f} ({center_candle['time']})", DEBUG_LOG_FILE)
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
    
    def _add_confirmed_pivot(self, pivot_data):
        """Thêm một pivot đã xác nhận"""
        try:
            # pivot_data phải có các trường bắt buộc
            if not all(key in pivot_data for key in ['type', 'price', 'time']):
                save_log("❌ Dữ liệu pivot không hợp lệ", DEBUG_LOG_FILE)
                return False
                
            # Kiểm tra xem pivot đã tồn tại chưa
            for pivot in self.confirmed_pivots:
                if pivot['time'] == pivot_data['time'] and pivot['price'] == pivot_data['price']:
                    save_log("⚠️ Pivot này đã tồn tại", DEBUG_LOG_FILE)
                    return False

            self.confirmed_pivots.append(pivot_data)
            save_log(f"✅ Đã thêm pivot: {pivot_data['type']} tại ${pivot_data['price']:,.2f} ({pivot_data['time']})", DEBUG_LOG_FILE)
            save_log(f"📊 Tổng số confirmed pivots: {len(self.confirmed_pivots)}", DEBUG_LOG_FILE)
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
                
    def _determine_pivot_type(self, current_price, direction):
        """
        Xác định loại pivot dựa trên so sánh với pivot tham chiếu
        Args:
            current_price (float): Giá của pivot cần xác định
            direction (str): 'high' hoặc 'low'
        Returns:
            str: Loại pivot (HH, HL, LH, LL) hoặc None nếu không xác định được
        """
        try:
            save_log("\n=== Phân loại Pivot ===", DEBUG_LOG_FILE)
            save_log(f"⏰ Thời điểm: {self.current_time}", DEBUG_LOG_FILE)
            save_log(f"💲 Giá: ${current_price:,.2f}", DEBUG_LOG_FILE)
            save_log(f"📍 Loại: {direction}", DEBUG_LOG_FILE)

            # 1. Nếu không có pivot nào
            if not self.confirmed_pivots:
                pivot_type = "HH" if direction == "high" else "LL"
                save_log(f"✨ Pivot đầu tiên -> {pivot_type}", DEBUG_LOG_FILE)
                return pivot_type

            # 2. Tìm pivot tham chiếu phù hợp
            current_time = datetime.strptime(self.current_time, '%H:%M')
            reference_pivot = None
            
            for pivot in reversed(self.confirmed_pivots):
                pivot_time = datetime.strptime(pivot['time'], '%H:%M')
                
                # Kiểm tra pivot tham chiếu cho ngày mới
                if 'is_reference' in pivot and pivot['is_reference']:
                    reference_pivot = pivot
                    save_log(f"📅 Sử dụng pivot tham chiếu từ ngày trước: {pivot['time']}", DEBUG_LOG_FILE)
                    break
                    
                # Kiểm tra pivot cùng loại trong ngày
                if current_time.hour >= pivot_time.hour:  # Cùng ngày
                    if pivot['direction'] == direction:
                        reference_pivot = pivot
                        save_log(f"🔄 Sử dụng pivot cùng loại gần nhất: {pivot['time']}", DEBUG_LOG_FILE)
                        break

            # 3. Nếu không tìm thấy pivot tham chiếu
            if not reference_pivot:
                pivot_type = "HH" if direction == "high" else "LL"
                save_log(f"✨ Pivot đầu tiên của loại {direction} -> {pivot_type}", DEBUG_LOG_FILE)
                return pivot_type

            # 4. So sánh với pivot tham chiếu
            if direction == "high":
                is_higher = current_price > reference_pivot['price']
                pivot_type = "HH" if is_higher else "LH"
                save_log(f"📊 So sánh High: ${current_price:,.2f} {'>' if is_higher else '<'} ${reference_pivot['price']:,.2f} ({reference_pivot['time']}) -> {pivot_type}", DEBUG_LOG_FILE)
            else:  # direction == "low"
                is_lower = current_price < reference_pivot['price']
                pivot_type = "LL" if is_lower else "HL"
                save_log(f"📊 So sánh Low: ${current_price:,.2f} {'<' if is_lower else '>'} ${reference_pivot['price']:,.2f} ({reference_pivot['time']}) -> {pivot_type}", DEBUG_LOG_FILE)

            save_log(f"✅ Kết luận: {pivot_type}", DEBUG_LOG_FILE)
            return pivot_type

        except Exception as e:
            save_log(f"❌ Lỗi khi xác định loại pivot: {str(e)}", DEBUG_LOG_FILE)
            save_log(traceback.format_exc(), DEBUG_LOG_FILE)
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
