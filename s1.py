import logging
import json
import pandas as pd
import os
import time
import pytz
from datetime import datetime
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
        self.pivot_points = []    # Lưu trữ các pivot point (high/low)
        self.confirmed_pivots = [] # Lưu trữ các pivot đã xác nhận (HH,LL,HL,LH)
        
        # Thời gian và user hiện tại
        self.current_time = None
        self.current_user = None
        
        save_log("🔄 Đã khởi tạo PivotData object với logic TradingView", DEBUG_LOG_FILE)
            
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
    
    def get_pivot_support_resistance(self, lookback: int = 20) -> dict:
        """
        Tính toán các mức hỗ trợ và kháng cự dựa trên pivot points
        Returns:
            Dict chứa các mức S/R và độ mạnh của chúng
        """
        try:
            if not hasattr(self, 'price_history') or len(self.price_history) < lookback:
                save_log(f"Không đủ dữ liệu để tính S/R (cần {lookback})", DEBUG_LOG_FILE)
                return {}

            # Lấy dữ liệu trong khoảng lookback
            recent_data = self.price_history[-lookback:]
            
            # Tính PP (Pivot Point)
            highs = [x['high'] for x in recent_data]
            lows = [x['low'] for x in recent_data]
            closes = [x['price'] for x in recent_data]
            
            pp = (max(highs) + min(lows) + closes[-1]) / 3
            
            # Tính các mức S/R
            r3 = pp + (max(highs) - min(lows))
            r2 = pp + (max(highs) - min(lows)) * 0.618  # Fibonacci ratio
            r1 = 2 * pp - min(lows)
            
            s1 = 2 * pp - max(highs)
            s2 = pp - (max(highs) - min(lows)) * 0.618
            s3 = pp - (max(highs) - min(lows))
            
            # Tính độ mạnh của mỗi mức
            def calculate_strength(level):
                touches = sum(1 for price in closes if abs(price - level) / level < 0.001)
                return min(touches / lookback * 100, 100)  # Độ mạnh tối đa 100%
            
            levels = {
                "R3": {"price": r3, "strength": calculate_strength(r3)},
                "R2": {"price": r2, "strength": calculate_strength(r2)},
                "R1": {"price": r1, "strength": calculate_strength(r1)},
                "PP": {"price": pp, "strength": calculate_strength(pp)},
                "S1": {"price": s1, "strength": calculate_strength(s1)},
                "S2": {"price": s2, "strength": calculate_strength(s2)},
                "S3": {"price": s3, "strength": calculate_strength(s3)}
            }
            
            save_log(f"Đã tính toán mức S/R: {levels}", DEBUG_LOG_FILE)
            return levels

        except Exception as e:
            save_log(f"Lỗi tính S/R: {str(e)}", DEBUG_LOG_FILE)
            return {}
    
    def improve_pivot_detection(self, price: float, time: str) -> tuple[bool, str]:
        """Cải thiện logic xác định pivot """
        try:
            # Lấy mức S/R
            support_resistance = self.get_pivot_support_resistance()
            if not support_resistance:
                return False, ""

            # Kiểm tra xem giá có gần mức S/R nào không
            MIN_DISTANCE = 0.001  # 0.1% cho phép dao động
            
            for level_name, level_data in support_resistance.items():
                level_price = level_data["price"]
                level_strength = level_data["strength"]
                
                price_diff = abs(price - level_price) / level_price
                
                if price_diff <= MIN_DISTANCE:
                    # Giá chạm mức S/R
                    if level_strength >= 70:  # Mức S/R mạnh
                        if "R" in level_name:  # Mức kháng cự
                            save_log(f"Phát hiện pivot tại mức kháng cự {level_name}: ${price:,.2f}", DEBUG_LOG_FILE)
                            return True, "High"
                        elif "S" in level_name:  # Mức hỗ trợ
                            save_log(f"Phát hiện pivot tại mức hỗ trợ {level_name}: ${price:,.2f}", DEBUG_LOG_FILE)
                            return True, "Low"
            
            return False, ""

        except Exception as e:
            save_log(f"Lỗi cải thiện pivot: {str(e)}", DEBUG_LOG_FILE)
            return False, ""
    
    def analyze_market_trend(self, short_period: int = 10, medium_period: int = 20, long_period: int = 50) -> dict:
        """
        Phân tích xu hướng thị trường sử dụng nhiều chỉ báo
        Returns:
            Dict chứa kết quả phân tích
        """
        try:
            if not hasattr(self, 'price_history') or len(self.price_history) < long_period:
                save_log(f"Không đủ dữ liệu để phân tích (cần {long_period})", DEBUG_LOG_FILE)
                return {}

            prices = [x['price'] for x in self.price_history]
            
            # Tính MA các chu kỳ
            def calculate_ma(period):
                if len(prices) < period:
                    return None
                return sum(prices[-period:]) / period
            
            short_ma = calculate_ma(short_period)
            medium_ma = calculate_ma(medium_period)
            long_ma = calculate_ma(long_period)
            
            # Tính RSI
            def calculate_rsi(period=14):
                if len(prices) < period + 1:
                    return None
                    
                deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
                gains = [d if d > 0 else 0 for d in deltas]
                losses = [-d if d < 0 else 0 for d in deltas]
                
                avg_gain = sum(gains[-period:]) / period
                avg_loss = sum(losses[-period:]) / period
                
                if avg_loss == 0:
                    return 100
                
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                return rsi
                
            rsi = calculate_rsi()
            
            # Xác định xu hướng
            trend = "Unknown"
            strength = 0
            
            if short_ma and medium_ma and long_ma:
                if short_ma > medium_ma > long_ma:
                    trend = "Uptrend"
                    strength = min(((short_ma/long_ma - 1) * 100), 100)
                elif short_ma < medium_ma < long_ma:
                    trend = "Downtrend"
                    strength = min(((1 - short_ma/long_ma) * 100), 100)
                else:
                    trend = "Sideways"
                    strength = 0
                    
            # Tính volatility
            if len(prices) >= 20:
                recent_prices = prices[-20:]
                avg_price = sum(recent_prices) / len(recent_prices)
                volatility = sum([abs(p - avg_price) / avg_price for p in recent_prices]) / len(recent_prices) * 100
            else:
                volatility = None

            result = {
                "trend": trend,
                "strength": strength,
                "short_ma": short_ma,
                "medium_ma": medium_ma,
                "long_ma": long_ma,
                "rsi": rsi,
                "volatility": volatility
            }
            
            save_log(f"Kết quả phân tích xu hướng: {result}", DEBUG_LOG_FILE)
            return result

        except Exception as e:
            save_log(f"Lỗi phân tích xu hướng: {str(e)}", DEBUG_LOG_FILE)
            return {}
   
    def add_user_pivot(self, pivot_type, price, time):
        """Thêm pivot từ user với kiểm tra logic chặt chẽ hơn"""
        try:
            # Kiểm tra loại pivot hợp lệ
            if pivot_type not in ["HH", "HL", "LH", "LL"]:
                save_log(f"❌ Loại pivot không hợp lệ: {pivot_type}", DEBUG_LOG_FILE)
                return False

            # Tạo pivot mới
            new_pivot = {
                "type": pivot_type,
                "price": float(price),
                "time": time,
                "source": "user"
            }

            # Kiểm tra logic với các pivot hiện có
            recent_pivots = self.get_recent_pivots(4)
            if recent_pivots:
                last_pivot = recent_pivots[0]
                
                # Log thông tin so sánh
                save_log("\n=== Kiểm Tra Logic User Pivot ===", DEBUG_LOG_FILE)
                save_log(f"Pivot mới: {pivot_type} tại ${price:,.2f} ({time})", DEBUG_LOG_FILE)
                save_log(f"Pivot trước: {last_pivot['type']} tại ${last_pivot['price']:,.2f} ({last_pivot['time']})", DEBUG_LOG_FILE)

                # Kiểm tra logic theo loại pivot
                if pivot_type == "HH" and price <= last_pivot['price']:
                    save_log("❌ HH phải có giá cao hơn pivot trước", DEBUG_LOG_FILE)
                    return False
                elif pivot_type == "LL" and price >= last_pivot['price']:
                    save_log("❌ LL phải có giá thấp hơn pivot trước", DEBUG_LOG_FILE)
                    return False
                elif pivot_type == "LH" and last_pivot['type'] == "HH" and price >= last_pivot['price']:
                    save_log("❌ LH phải có giá thấp hơn HH trước", DEBUG_LOG_FILE)
                    return False
                elif pivot_type == "HL" and last_pivot['type'] == "LL" and price <= last_pivot['price']:
                    save_log("❌ HL phải có giá cao hơn LL trước", DEBUG_LOG_FILE)
                    return False

            # Thêm pivot mới
            self.user_pivots.append(new_pivot)
            save_log(f"✅ Đã thêm user pivot: {pivot_type} tại ${price:,.2f} ({time})", DEBUG_LOG_FILE)
            return True

        except Exception as e:
            save_log(f"❌ Lỗi khi thêm user pivot: {str(e)}", DEBUG_LOG_FILE)
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
    
    def _can_add_pivot(self, price):
        """Kiểm tra có thể thêm pivot không"""
        try:
            all_pivots = self.get_all_pivots()
            if not all_pivots:
                return True
                
            last_pivot = all_pivots[-1]
            time_diff = self._calculate_time_diff(last_pivot["time"])
            
            if time_diff < self.MIN_PIVOT_DISTANCE:
                return False
                
            return True
            
        except Exception as e:
            save_log(f"Lỗi khi kiểm tra can_add_pivot: {str(e)}", DEBUG_LOG_FILE)
            return False       
 
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
            # Chỉ lấy từ confirmed_pivots vì không còn user_pivots
            save_log("\n=== Lấy 4 pivot gần nhất ===", DEBUG_LOG_FILE)
            save_log(f"Tổng số pivot: {len(self.confirmed_pivots)}", DEBUG_LOG_FILE)
            
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

    def check_pattern(self):
        """Tạm thời vô hiệu hóa việc kiểm tra pattern"""
        save_log("\n⚠️ Chức năng check pattern đang tạm thời bị vô hiệu hóa", DEBUG_LOG_FILE)
        return False, ""
    
    def classify_pivot(self, new_pivot):
        """Phân loại pivot theo logic TradingView"""
        try:
            if len(self.pivot_points) < 5:
                return None  # Cần ít nhất 5 pivot để phân loại

            # Lấy 5 pivot gần nhất (bao gồm pivot mới)
            recent_points = self.pivot_points[-5:]
            if len(recent_points) < 5:
                return None

            # Gán các giá trị theo cách đặt tên trong TradingView
            a = new_pivot['price']  # Pivot hiện tại
            b = recent_points[-2]['price']  # Pivot trước đó
            c = recent_points[-3]['price']  # Pivot trước b
            d = recent_points[-4]['price']  # Pivot trước c
            e = recent_points[-5]['price']  # Pivot trước d

            # Phân loại pivot theo logic TradingView
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

            # Tạo DataFrame chính
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

            # Sử dụng ExcelWriter với xlsxwriter
            with pd.ExcelWriter('pivots.xlsx', engine='xlsxwriter') as writer:
                # Sheet chính
                df_main.to_excel(writer, sheet_name='TestData', index=False, startrow=2)
                workbook = writer.book
                worksheet = writer.sheets['TestData']
                
                # Thêm confirmed text ở đầu
                confirmed_text = " / ".join([
                    f"{p['type']} {p['time']} ${p['price']:,.2f}" 
                    for p in self.confirmed_pivots
                ])
                worksheet.write(0, 0, "Confirmed Pivots:")
                worksheet.write(0, 1, confirmed_text)
                
                # Định dạng các cột
                price_format = workbook.add_format({'num_format': '$#,##0.00'})
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#D9D9D9'
                })
                type_format = {
                    'HH': workbook.add_format({'font_color': 'green', 'bold': True}),
                    'LL': workbook.add_format({'font_color': 'red', 'bold': True}),
                    'HL': workbook.add_format({'font_color': 'orange'}),
                    'LH': workbook.add_format({'font_color': 'blue'})
                }
                
                # Áp dụng định dạng cho header và cột
                for col, width in {'A:A': 10, 'B:B': 8, 'C:C': 15, 'D:D': 10}.items():
                    worksheet.set_column(col, width)
                
                # Format headers
                worksheet.write(2, 0, 'Time', header_format)
                worksheet.write(2, 1, 'Type', header_format)
                worksheet.write(2, 2, 'Price', header_format)
                worksheet.write(2, 3, 'Change%', header_format)
                
                # Format data
                for idx, row in df_main.iterrows():
                    row_pos = idx + 3
                    worksheet.write(row_pos, 0, row['Time'])
                    worksheet.write(row_pos, 1, row['Type'], type_format.get(row['Type']))
                    worksheet.write(row_pos, 2, row['Price'], price_format)
                    
                    # Format % thay đổi
                    if idx > 0:
                        change_format = workbook.add_format({
                            'num_format': '+0.00%;-0.00%',
                            'font_color': 'green' if row['Change%'] > 0 else 'red'
                        })
                        worksheet.write(row_pos, 3, row['Change%']/100, change_format)

                # Tạo biểu đồ
                chart = workbook.add_chart({'type': 'line'})
                
                # Thêm series cho giá
                chart.add_series({
                    'name': 'Price',
                    'categories': f"='TestData'!$A$4:$A${len(df_main) + 3}",
                    'values': f"='TestData'!$C$4:$C${len(df_main) + 3}",
                    'marker': {'type': 'circle'},
                    'data_labels': {'value': True, 'num_format': '$#,##0.00'}
                })
                
                # Định dạng biểu đồ
                chart.set_title({'name': 'Pivot Points Analysis'})
                chart.set_x_axis({
                    'name': 'Time',
                    'num_format': 'hh:mm'
                })
                chart.set_y_axis({'name': 'Price (USD)'})
                chart.set_size({'width': 720, 'height': 400})
                
                # Thêm biểu đồ vào sheet
                worksheet.insert_chart('H2', chart)
                
                # Thêm thống kê
                stats_row = len(df_main) + 5
                worksheet.write(stats_row, 0, "Thống kê:", header_format)
                worksheet.write(stats_row + 1, 0, "Tổng số pivot:")
                worksheet.write(stats_row + 1, 1, len(self.confirmed_pivots))
                worksheet.write(stats_row + 2, 0, "Tổng số nến:")
                worksheet.write(stats_row + 2, 1, len(self.price_history))

            save_log(f"Đã lưu dữ liệu pivot vào Excel với {len(self.confirmed_pivots)} điểm", DEBUG_LOG_FILE)
            
        except Exception as e:
            error_msg = f"Lỗi khi lưu file Excel: {str(e)}"
            save_log(error_msg, DEBUG_LOG_FILE)
            logger.error(error_msg)
    def _get_pattern_for_pivot(self, current_pivot, all_pivots):
        """Xác định pattern cho một pivot cụ thể"""
        try:
            # Lấy 4 pivot trước current_pivot
            idx = all_pivots.index(current_pivot)
            if idx < 4:
                return "Chưa đủ dữ liệu"
                
            prev_pivots = all_pivots[idx-4:idx]
            pivot_types = [p['type'] for p in prev_pivots] + [current_pivot['type']]
            
            # Kiểm tra các pattern đã định nghĩa
            pattern_sequences = {
                "Tăng mạnh": ["HH", "HH", "HH", "HH", "HH"],
                "Giảm mạnh": ["LL", "LL", "LL", "LL", "LL"],
                "Đảo chiều tăng": ["LL", "HL", "HH", "HL", "HH"],
                "Đảo chiều giảm": ["HH", "LH", "LL", "LH", "LL"]
            }
            
            for pattern_name, sequence in pattern_sequences.items():
                if pivot_types == sequence:
                    return pattern_name
                    
            return "Không xác định"
            
        except Exception as e:
            save_log(f"❌ Lỗi khi xác định pattern: {str(e)}", DEBUG_LOG_FILE)
            return "Lỗi xác định" 

    def get_all_pivots(self):
        """Lấy tất cả các pivot theo thứ tự thời gian"""
        try:
            # Chỉ lấy từ confirmed_pivots vì không còn user_pivots
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
            
    def add_user_pivot(self, pivot_type, price, time):
        """Thêm pivot từ user với logic mới"""
        try:
            # Kiểm tra loại pivot hợp lệ
            if pivot_type not in ["HH", "HL", "LH", "LL"]:
                save_log(f"❌ Loại pivot không hợp lệ: {pivot_type}", DEBUG_LOG_FILE)
                return False

            # Tạo pivot mới
            new_pivot = {
                "type": pivot_type,
                "price": float(price),
                "time": time
            }

            # Kiểm tra logic với pivot đã có
            recent_pivots = self.get_recent_pivots(4)
            if recent_pivots:
                last_pivot = recent_pivots[0]
                
                # Log thông tin so sánh
                save_log("\n=== Kiểm tra Logic User Pivot ===", DEBUG_LOG_FILE)
                save_log(f"Pivot mới: {pivot_type} tại ${price:,.2f} ({time})", DEBUG_LOG_FILE)
                save_log(f"Pivot trước: {last_pivot['type']} tại ${last_pivot['price']:,.2f} ({last_pivot['time']})", DEBUG_LOG_FILE)

                # Kiểm tra logic
                if not self._validate_pivot_sequence(last_pivot, new_pivot):
                    return False

            # Thêm pivot mới vào confirmed_pivots
            if new_pivot not in self.confirmed_pivots:
                self.confirmed_pivots.append(new_pivot)
                save_log(f"✅ Đã thêm pivot: {pivot_type} tại ${price:,.2f} ({time})", DEBUG_LOG_FILE)
                return True

            return False

        except Exception as e:
            save_log(f"❌ Lỗi khi thêm user pivot: {str(e)}", DEBUG_LOG_FILE)
            return False

    def _validate_pivot_sequence(self, prev_pivot, new_pivot):
        """Kiểm tra tính hợp lệ của chuỗi pivot"""
        try:
            # HH phải cao hơn pivot trước
            if new_pivot['type'] == 'HH' and new_pivot['price'] <= prev_pivot['price']:
                save_log("❌ HH phải có giá cao hơn pivot trước", DEBUG_LOG_FILE)
                return False
                
            # LL phải thấp hơn pivot trước
            if new_pivot['type'] == 'LL' and new_pivot['price'] >= prev_pivot['price']:
                save_log("❌ LL phải có giá thấp hơn pivot trước", DEBUG_LOG_FILE)
                return False
                
            # LH phải thấp hơn HH trước
            if new_pivot['type'] == 'LH' and prev_pivot['type'] == 'HH' and new_pivot['price'] >= prev_pivot['price']:
                save_log("❌ LH phải có giá thấp hơn HH trước", DEBUG_LOG_FILE)
                return False
                
            # HL phải cao hơn LL trước
            if new_pivot['type'] == 'HL' and prev_pivot['type'] == 'LL' and new_pivot['price'] <= prev_pivot['price']:
                save_log("❌ HL phải có giá cao hơn LL trước", DEBUG_LOG_FILE)
                return False
                
            save_log("✅ Pivot sequence hợp lệ", DEBUG_LOG_FILE)
            return True
                
        except Exception as e:
            save_log(f"❌ Lỗi khi validate pivot sequence: {str(e)}", DEBUG_LOG_FILE)
            return False
    
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
        # Thay đổi interval từ "5m" sang "30m"
        klines = binance_client.futures_klines(symbol="BTCUSDT", interval="30m", limit=2)
        last_candle = klines[-2]  # Ensure we get the closed candle
        high_price = float(last_candle[2])
        low_price = float(last_candle[3])
        close_price = float(last_candle[4])
        
        price_data = {
            "high": high_price,
            "low": low_price,
            "price": close_price
        }
        pivot_data.add_price_data(price_data)
        
        save_log(f"Thu thập dữ liệu nến 30m: Cao nhất = {high_price}, Thấp nhất = {low_price}", DEBUG_LOG_FILE)
        
        detect_pivot(high_price, "H")
        detect_pivot(low_price, "L")
        pivot_data.save_to_excel()
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
     

def _create_alert_message(pattern_name, current_price, recent_pivots):
    """Tạo thông báo chi tiết khi phát hiện mẫu hình"""
    vietnam_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Xác định loại mẫu hình và biểu tượng
    if "bullish" in pattern_name.lower():
        pattern_symbol = "🟢"
        direction = "tăng"
    else:
        pattern_symbol = "🔴"
        direction = "giảm"
        
    message = (
        f"{pattern_symbol} CẢNH BÁO MẪU HÌNH {direction.upper()} - {vietnam_time}\n\n"
        f"Giá hiện tại: ${current_price:,.2f}\n"
        f"Mẫu hình: {pattern_name}\n\n"
        f"5 pivot gần nhất:\n"
    )
    
    # Thêm thông tin về 5 pivot gần nhất
    for i, pivot in enumerate(recent_pivots[::-1], 1):
        message += f"{i}. {pivot['type']}: ${pivot['price']:,.2f} ({pivot['time']})\n"
        
    return message

def send_alert(message):
    """Gửi cảnh báo qua Telegram với thông tin chi tiết"""
    try:
        bot = Bot(token=TOKEN)
        bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode='HTML'
        )
        save_log("Đã gửi cảnh báo mẫu hình", DEBUG_LOG_FILE)
    except Exception as e:
        save_log(f"Lỗi gửi cảnh báo: {str(e)}", DEBUG_LOG_FILE)

def moc(update: Update, context: CallbackContext):
    """ Handles the /moc command to receive multiple pivot points and resets logic."""
    try:
        args = context.args
        
        logger.info(f"Received /moc command with args: {args}")
        save_log(f"Received /moc command with args: {args}", DEBUG_LOG_FILE)
        
        if len(args) < 4 or (len(args) - 1) % 3 != 0:
            update.message.reply_text("⚠️ Sai định dạng! Dùng: /moc btc lh 82000 13:30 hl 81000 14:00 hh 83000 14:30")
            return
        
        asset = args[0].lower()
        if asset != "btc":
            update.message.reply_text("⚠️ Chỉ hỗ trợ BTC! Ví dụ: /moc btc lh 82000 13:30 hl 81000 14:00 hh 83000 14:30")
            return
            
        # Xóa dữ liệu cũ
        pivot_data.clear_all()
        
        # Ghi nhận các mốc mới
        valid_pivots = []
        adjusted_times = []
        current_time = datetime.now()  # Lấy thời gian hiện tại
        
        # Kiểm tra thứ tự thời gian
        time_points = []
        for i in range(1, len(args), 3):
            try:
                time = args[i + 2].replace('h', ':')
                time_obj = datetime.strptime(time, "%H:%M")
                time_points.append(time_obj)
            except ValueError:
                continue

        if time_points:
            if time_points != sorted(time_points):
                update.message.reply_text("⚠️ Các mốc thời gian phải được nhập theo thứ tự tăng dần!")
                return
        
        for i in range(1, len(args), 3):
            pivot_type = args[i].upper()
            if pivot_type not in ["HH", "HL", "LH", "LL"]:
                update.message.reply_text(f"⚠️ Loại pivot không hợp lệ: {pivot_type}. Chỉ chấp nhận: HH, HL, LH, LL")
                return

            # Validate giá
            try:
                price = float(args[i + 1])
                if price <= 0:
                    update.message.reply_text(f"⚠️ Giá phải lớn hơn 0: {args[i + 1]}")
                    return
                if price > 500000:  # Giới hạn giá tối đa hợp lý cho BTC
                    update.message.reply_text(f"⚠️ Giá vượt quá giới hạn cho phép: {args[i + 1]}")
                    return
            except ValueError:
                update.message.reply_text(f"⚠️ Giá không hợp lệ: {args[i + 1]}")
                return

            # Validate và xử lý thời gian
            time = args[i + 2].replace('h', ':')
            try:
                time_obj = datetime.strptime(time, "%H:%M")
                
                # Làm tròn về mốc 30 phút gần nhất
                minutes = time_obj.minute
                if minutes % 30 != 0:
                    adjusted_minutes = 30 * (minutes // 30)
                    original_time = time
                    time = time_obj.replace(minute=adjusted_minutes).strftime("%H:%M")
                    adjusted_times.append((original_time, time))
                    save_log(f"Đã điều chỉnh thời gian từ {original_time} thành {time} cho phù hợp với timeframe 30m", DEBUG_LOG_FILE)
            except ValueError:
                update.message.reply_text(f"⚠️ Lỗi: Định dạng thời gian không đúng! Sử dụng HH:MM (ví dụ: 14:00, 14:30)")
                return

            # Thêm pivot mới
            if pivot_data.add_user_pivot(pivot_type, price, time):
                valid_pivots.append({"type": pivot_type, "price": price, "time": time})
            else:
                update.message.reply_text(f"⚠️ Không thể thêm pivot: {pivot_type} at {time}")
                return
        
        # Kiểm tra tính hợp lệ của chuỗi pivot
        if len(valid_pivots) >= 2:
            for i in range(1, len(valid_pivots)):
                curr_pivot = valid_pivots[i]
                prev_pivot = valid_pivots[i-1]
                
                save_log(f"Kiểm tra logic: {curr_pivot['type']} (${curr_pivot['price']}) vs {prev_pivot['type']} (${prev_pivot['price']})", DEBUG_LOG_FILE)
                
                # Logic kiểm tra mới
                if curr_pivot['type'] == "LH":
                    if prev_pivot['type'] == "LL":
                        # LH phải cao hơn LL trước đó
                        if curr_pivot['price'] <= prev_pivot['price']:
                            error_msg = f"⚠️ Lỗi logic: LH tại {curr_pivot['time']} phải có giá cao hơn LL trước đó!"
                            save_log(error_msg, DEBUG_LOG_FILE)
                            update.message.reply_text(error_msg)
                            return
                    elif prev_pivot['type'] == "HH":
                        # LH phải thấp hơn HH trước đó 
                        if curr_pivot['price'] >= prev_pivot['price']:
                            error_msg = f"⚠️ Lỗi logic: LH tại {curr_pivot['time']} phải có giá thấp hơn HH trước đó!"
                            save_log(error_msg, DEBUG_LOG_FILE)
                            update.message.reply_text(error_msg)
                            return
                        
                elif curr_pivot['type'] == "HL":
                    if prev_pivot['type'] in ["LH", "HH"]:
                        # HL phải thấp hơn đỉnh trước đó (LH hoặc HH)
                        if curr_pivot['price'] >= prev_pivot['price']:
                            error_msg = f"⚠️ Lỗi logic: HL tại {curr_pivot['time']} phải có giá thấp hơn {prev_pivot['type']} trước đó!"
                            save_log(error_msg, DEBUG_LOG_FILE)
                            update.message.reply_text(error_msg)
                            return
                    elif prev_pivot['type'] == "LL":
                        # HL phải cao hơn LL trước đó
                        if curr_pivot['price'] <= prev_pivot['price']:
                            error_msg = f"⚠️ Lỗi logic: HL tại {curr_pivot['time']} phải có giá cao hơn LL trước đó!"
                            save_log(error_msg, DEBUG_LOG_FILE)
                            update.message.reply_text(error_msg)
                            return
                        
                elif curr_pivot['type'] == "HH":
                    # HH luôn phải cao hơn pivot trước đó
                    if curr_pivot['price'] <= prev_pivot['price']:
                        error_msg = f"⚠️ Lỗi logic: HH tại {curr_pivot['time']} phải có giá cao hơn pivot trước đó!"
                        save_log(error_msg, DEBUG_LOG_FILE)
                        update.message.reply_text(error_msg)
                        return
                        
                elif curr_pivot['type'] == "LL":
                    # LL luôn phải thấp hơn pivot trước đó
                    if curr_pivot['price'] >= prev_pivot['price']:
                        error_msg = f"⚠️ Lỗi logic: LL tại {curr_pivot['time']} phải có giá thấp hơn pivot trước đó!"
                        save_log(error_msg, DEBUG_LOG_FILE)
                        update.message.reply_text(error_msg)
                        return
                        
                save_log(f"Pivot {curr_pivot['type']} hợp lệ", DEBUG_LOG_FILE)
        
        # Ghi đè dữ liệu vào pattern log
        with open(PATTERN_LOG_FILE, "w", encoding="utf-8") as f:
            f.write("=== Pattern Log Reset ===\n")

        save_log(f"User Pivots Updated: {pivot_data.user_pivots}", LOG_FILE)
        save_log(f"User Pivots Updated: {pivot_data.user_pivots}", PATTERN_LOG_FILE)
        save_to_excel()

        # Tạo phản hồi chi tiết cho người dùng
        response = "✅ Đã nhận các mốc:\n"
        for pivot in valid_pivots:
            response += f"• {pivot['type']} tại ${pivot['price']:,.2f} ({pivot['time']})\n"
        
        # Thêm thông báo về các điều chỉnh thời gian (nếu có)
        if adjusted_times:
            response += "\nℹ️ Đã điều chỉnh các mốc thời gian sau cho phù hợp với timeframe 30m:\n"
            for original, adjusted in adjusted_times:
                response += f"• {original} → {adjusted}\n"
            
        update.message.reply_text(response)
        logger.info(f"User Pivots Updated: {pivot_data.user_provided_pivots}")
        
    except Exception as e:
        error_msg = f"Lỗi xử lý lệnh /moc: {str(e)}"
        logger.error(error_msg)
        save_log(error_msg, DEBUG_LOG_FILE)
        update.message.reply_text(f"⚠️ Có lỗi xảy ra: {str(e)}")

def main():
    """ Main entry point to start the bot."""
    try:
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher
        job_queue = updater.job_queue
    
        dp.add_handler(CommandHandler("moc", moc))
        
        schedule_next_run(job_queue)  # Schedule the first execution at the next 5-minute mark
        
        print("Bot is running...")
        logger.info("Bot started successfully.")
        updater.start_polling()
        updater.idle()
    except Exception as e:
        logger.error(f"Error in main: {e}")
        save_log(f"Error in main: {e}", DEBUG_LOG_FILE)

if __name__ == "__main__":
    main()
