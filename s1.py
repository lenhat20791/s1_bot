import logging
import json
import pandas as pd
import os
import time
import pytz
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
        self.pivot_points.clear()
        self.confirmed_pivots.clear()
        
        save_log("\n=== Reset Toàn Bộ Dữ Liệu ===", DEBUG_LOG_FILE)
        save_log("✅ Đã xóa price history", DEBUG_LOG_FILE)
        save_log("✅ Đã xóa pivot points", DEBUG_LOG_FILE)
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
        """Phát hiện pivot với logic TradingView đơn giản hóa"""
        try:
            # 1. Kiểm tra đủ dữ liệu
            if len(self.price_history) < (self.LEFT_BARS + self.RIGHT_BARS + 1):
                save_log(f"⏳ Đang thu thập dữ liệu: {len(self.price_history)}/{self.LEFT_BARS + self.RIGHT_BARS + 1} nến", DEBUG_LOG_FILE)
                return None

            # 2. Lấy center candle và các nến xung quanh
            center_idx = self.LEFT_BARS
            center_candle = self.price_history[center_idx]
            left_bars = self.price_history[:center_idx]
            right_bars = self.price_history[center_idx + 1:]

            pivot_found = False
            pivot_type = None
            pivot_price = None

            # 3. Logic TV đơn giản: So sánh với các nến xung quanh
            if direction.lower() == "high":
                # Kiểm tra pivot high
                if all(center_candle['high'] > bar['high'] for bar in left_bars) and \
                   all(center_candle['high'] > bar['high'] for bar in right_bars):
                    pivot_found = True
                    pivot_price = center_candle['high']
                    # Xác định loại pivot high (HH hoặc LH)
                    pivot_type = self._determine_pivot_type(pivot_price, "high")
                    
            elif direction.lower() == "low":
                # Kiểm tra pivot low
                if all(center_candle['low'] < bar['low'] for bar in left_bars) and \
                   all(center_candle['low'] < bar['low'] for bar in right_bars):
                    pivot_found = True
                    pivot_price = center_candle['low']
                    # Xác định loại pivot low (LL hoặc HL)
                    pivot_type = self._determine_pivot_type(pivot_price, "low")

            # 4. Nếu tìm thấy pivot, thêm vào danh sách
            if pivot_found and pivot_type:
                save_log(f"✅ Phát hiện {pivot_type} tại ${pivot_price:,.2f}", DEBUG_LOG_FILE)
                return self._add_confirmed_pivot(pivot_type, pivot_price)

            return None

        except Exception as e:
            save_log(f"❌ Lỗi khi phát hiện pivot: {str(e)}", DEBUG_LOG_FILE)
            return None       
    
 
    def _add_confirmed_pivot(self, pivot_type, price, current_time=None):
        """Thêm pivot đã được xác nhận với logging chi tiết"""
        try:
            # Nếu không có current_time, dùng self.current_time
            pivot_time = current_time if current_time else self.current_time
            
            save_log("\n=== Thêm Confirmed Pivot ===", DEBUG_LOG_FILE)
            save_log(f"Type: {pivot_type}", DEBUG_LOG_FILE)
            save_log(f"Price: ${price:,.2f}", DEBUG_LOG_FILE)
            save_log(f"Time: {pivot_time}", DEBUG_LOG_FILE)
            
            # Tạo pivot mới với key 'type' rõ ràng
            new_pivot = {
                "type": pivot_type,  # Đảm bảo có key 'type'
                "price": float(price),
                "time": pivot_time
            }
            
            # Log thông tin pivot mới
            save_log(f"New pivot data: {new_pivot}", DEBUG_LOG_FILE)

            # Kiểm tra trùng lặp
            if new_pivot not in self.confirmed_pivots:
                self.confirmed_pivots.append(new_pivot)
                save_log(f"✅ Đã thêm pivot: {pivot_type} tại ${price:,.2f} ({pivot_time})", DEBUG_LOG_FILE)
                save_log(f"📊 Tổng số confirmed pivots: {len(self.confirmed_pivots)}", DEBUG_LOG_FILE)
                return True

            save_log("⚠️ Pivot này đã tồn tại", DEBUG_LOG_FILE)
            return False

        except Exception as e:
            save_log(f"❌ Lỗi khi thêm confirmed pivot: {str(e)}", DEBUG_LOG_FILE)
            save_log(f"Stack trace: {traceback.format_exc()}", DEBUG_LOG_FILE)
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
                    'time': new_pivot['time']
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
                save_log("Không có dữ liệu pivot để lưu", DEBUG_LOG_FILE)
                return

            # Đơn giản hóa dữ liệu chính
            main_data = []
            for pivot in self.confirmed_pivots:
                # Tính % thay đổi so với pivot trước
                prev_pivot = next((p for p in self.confirmed_pivots 
                                 if p['time'] < pivot['time']), None)
                price_change = ((pivot['price'] - prev_pivot['price'])/prev_pivot['price'] * 100) if prev_pivot else 0
                
                main_data.append({
                    'Time': pivot['time'],
                    'Type': pivot['type'],
                    'Price': pivot['price'],
                    'Change%': price_change
                })
            
            df_main = pd.DataFrame(main_data)

            # Sử dụng ExcelWriter
            with pd.ExcelWriter('pivots.xlsx', engine='xlsxwriter') as writer:
                # Sheet chính
                df_main.to_excel(writer, sheet_name='Pivot Analysis', index=False)
                workbook = writer.book
                worksheet = writer.sheets['Pivot Analysis']
                
                # Định dạng cột
                formats = {
                    'Price': workbook.add_format({'num_format': '$#,##0.00'}),
                    'Change%': workbook.add_format({'num_format': '+0.00%;-0.00%'}),
                    'Type': {
                        'HH': workbook.add_format({'font_color': 'green', 'bold': True}),
                        'LL': workbook.add_format({'font_color': 'red', 'bold': True}),
                        'HL': workbook.add_format({'font_color': 'orange'}),
                        'LH': workbook.add_format({'font_color': 'blue'})
                    }
                }
                
                # Áp dụng định dạng
                for idx, row in df_main.iterrows():
                    row_pos = idx + 1
                    worksheet.write(row_pos, df_main.columns.get_loc('Time'), row['Time'])
                    worksheet.write(row_pos, df_main.columns.get_loc('Type'), 
                                 row['Type'], formats['Type'][row['Type']])
                    worksheet.write(row_pos, df_main.columns.get_loc('Price'), 
                                 row['Price'], formats['Price'])
                    worksheet.write(row_pos, df_main.columns.get_loc('Change%'), 
                                 row['Change%']/100, formats['Change%'])

                # Thêm biểu đồ
                chart = workbook.add_chart({'type': 'line'})
                chart.add_series({
                    'name': 'Price',
                    'categories': f'=Pivot Analysis!$A$2:$A${len(df_main) + 1}',
                    'values': f'=Pivot Analysis!$C$2:$C${len(df_main) + 1}',
                    'marker': {'type': 'circle'},
                    'data_labels': {'value': True, 'num_format': '$#,##0.00'}
                })
                
                # Định dạng biểu đồ
                chart.set_title({'name': 'Pivot Points Analysis'})
                chart.set_size({'width': 720, 'height': 400})
                worksheet.insert_chart('G2', chart)

            save_log(f"✅ Đã lưu {len(self.confirmed_pivots)} pivot vào Excel", DEBUG_LOG_FILE)
                
        except Exception as e:
            save_log(f"❌ Lỗi khi lưu Excel: {str(e)}", DEBUG_LOG_FILE)
            
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
        """Xác định loại pivot dựa trên logic TV"""
        try:
            # Lấy pivot gần nhất cùng loại (high/low)
            recent_pivots = self.get_recent_pivots(3)  # Chỉ cần 3 pivot gần nhất
            if not recent_pivots:
                # Pivot đầu tiên
                return "HH" if direction == "high" else "LL"

            last_pivot = None
            for pivot in recent_pivots:
                # Tìm pivot cùng loại gần nhất
                if (direction == "high" and pivot['type'] in ['HH', 'LH']) or \
                   (direction == "low" and pivot['type'] in ['LL', 'HL']):
                    last_pivot = pivot
                    break

            if not last_pivot:
                return "HH" if direction == "high" else "LL"

            # Logic phân loại đơn giản theo TV
            if direction == "high":
                return "HH" if current_price > last_pivot['price'] else "LH"
            else:
                return "LL" if current_price < last_pivot['price'] else "HL"

        except Exception as e:
            save_log(f"❌ Lỗi khi xác định loại pivot: {str(e)}", DEBUG_LOG_FILE)
            return None   
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
