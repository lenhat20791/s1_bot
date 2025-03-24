import json
import os
from datetime import datetime, timedelta
import pytz
import re
import traceback

# Đường dẫn đến file lưu trữ các pivot ban đầu
INIT_PIVOTS_FILE = "data/initial_pivots.json"

def save_initial_pivots(pivots):
    """Lưu danh sách pivot ban đầu vào file"""
    try:
        # Đảm bảo thư mục data tồn tại
        if not os.path.exists("data"):
            os.makedirs("data")
            
        with open(INIT_PIVOTS_FILE, "w", encoding="utf-8") as f:
            json.dump(pivots, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Lỗi khi lưu pivot ban đầu: {str(e)}")
        return False

def load_initial_pivots():
    """Đọc danh sách pivot ban đầu từ file"""
    try:
        if os.path.exists(INIT_PIVOTS_FILE):
            with open(INIT_PIVOTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"Lỗi khi đọc pivot ban đầu: {str(e)}")
        return []

def parse_date(date_str):
    """
    Phân tích chuỗi ngày tháng ở các định dạng khác nhau
    Hỗ trợ:
    - YYYY-MM-DD (2025-03-23)
    - DD-MM-YYYY (23-03-2025)
    """
    try:
        # Kiểm tra các định dạng ngày
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):  # YYYY-MM-DD
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
        elif re.match(r'^\d{2}-\d{2}-\d{4}$', date_str):  # DD-MM-YYYY
            return datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d")
        else:
            # Định dạng không được hỗ trợ, sử dụng ngày hiện tại
            return datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime("%Y-%m-%d")
    except Exception:
        # Nếu có lỗi, sử dụng ngày hiện tại
        return datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime("%Y-%m-%d")

def parse_pivot_input(pivot_text):
    """
    Parse input với format: type:price:date:time
    Hỗ trợ nhiều format thời gian:
    - HH:MM (14:30)
    - HhMM (14h30)
    """
    try:
        print("\n=== DEBUG LOG ===")
        print(f"Input: {pivot_text}")
        
        # 1. Tách và validate input
        parts = pivot_text.strip().split(':')
        print(f"Parts: {parts}")
        
        if len(parts) != 4:
            print(f"❌ Lỗi: Cần 4 phần, nhận được {len(parts)}")
            return None
        
        pivot_type, price_str, date_str, time_str = parts
        
        # 2. Xử lý pivot type
        pivot_type = pivot_type.upper()
        if pivot_type not in ["LL", "LH", "HL", "HH"]:
            print(f"❌ Lỗi: Loại pivot không hợp lệ: {pivot_type}")
            return None
            
        # 3. Xử lý giá
        try:
            price = float(price_str)
            if price <= 0:
                print(f"❌ Lỗi: Giá không hợp lệ: {price}")
                return None
        except ValueError:
            print(f"❌ Lỗi: Không thể chuyển đổi giá: {price_str}")
            return None
            
        # 4. Xử lý ngày
        try:
            # Chuẩn hóa format ngày
            date_str = date_str.replace('/', '-')
            date_parts = date_str.split('-')
            
            if len(date_parts[0]) == 4:  # YYYY-MM-DD
                year, month, day = map(int, date_parts)
            else:  # DD-MM-YYYY
                day, month, year = map(int, date_parts)
                
            vn_date = f"{year:04d}-{month:02d}-{day:02d}"
            
            # Validate ngày
            datetime.strptime(vn_date, '%Y-%m-%d')
            
        except Exception as e:
            print(f"❌ Lỗi xử lý ngày: {str(e)}")
            return None
            
        # 5. Xử lý thời gian - hỗ trợ nhiều format
        try:
            # Loại bỏ các ký tự không cần thiết
            time_str = time_str.lower().replace('h', ':').strip()
            
            # Xử lý format HH:MM
            if ':' in time_str:
                hour, minute = map(int, time_str.split(':'))
            else:
                # Format không hợp lệ
                print(f"❌ Lỗi: Format thời gian không hợp lệ: {time_str}")
                return None
                
            # Validate thời gian
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                print(f"❌ Lỗi: Thời gian không hợp lệ: {hour}:{minute}")
                return None
                
            vn_time = f"{hour:02d}:{minute:02d}"
            
        except Exception as e:
            print(f"❌ Lỗi xử lý thời gian: {str(e)}")
            return None
            
        # 6. Tạo kết quả
        result = {
            "type": pivot_type,
            "price": price,
            "vn_date": vn_date,
            "vn_time": vn_time,
            "direction": "high" if pivot
