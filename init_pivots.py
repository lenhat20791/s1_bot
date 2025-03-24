# init_pivots.py
import json
import os
from datetime import datetime, timedelta
import pytz
import re

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
        
        # Lấy ngày hiện tại theo múi giờ VN
        now = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
        default_vn_date = now.strftime('%Y-%m-%d')
        
        # Xử lý định dạng thời gian để đảm bảo có HH:MM
        if len(parts) == 3:  # Định dạng không có ngày: LL:83597:06:30
            time_str = parts[2]
            vn_date = default_vn_date
        else:  # Có ngày: LL:83597:23-03-2025:06:30 hoặc LL:83597:23/03/2025:06:30
            date_part = parts[2].replace('/', '-')  # Chuẩn hóa dấu phân cách
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
        
        # Đảm bảo vn_time có định dạng HH:MM chính xác
        if ":" not in time_str:
            # Nếu time_str chỉ chứa giờ không có phút, thêm ":00"
            if len(time_str) <= 2:
                vn_time = f"{time_str.zfill(2)}:00"
            elif len(time_str) == 4:  # Định dạng 0630 -> 06:30
                vn_time = f"{time_str[:2]}:{time_str[2:]}"
            else:
                vn_time = f"{time_str[:2]}:00"  # Lấy 2 số đầu làm giờ
        else:
            hour, minute = time_str.split(':')
            vn_time = f"{hour.zfill(2)}:{minute.zfill(2)}"  # Đảm bảo đủ 2 chữ số
            
        # Validate thời gian
        try:
            hour = int(vn_time.split(':')[0])
            minute = int(vn_time.split(':')[1])
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                print(f"Thời gian không hợp lệ: {vn_time}")
                return None
        except:
            print(f"Định dạng thời gian không hợp lệ: {vn_time}")
            return None
            
        # Xác định direction dựa vào loại pivot
        if pivot_type in ["HH", "LH"]:
            direction = "high"
        else:  # LL, HL
            direction = "low"
            
        # Validate ngày tháng
        try:
            datetime.strptime(vn_date, '%Y-%m-%d')
        except ValueError:
            print(f"Định dạng ngày không hợp lệ: {vn_date}")
            return None
            
        # Trả về pivot đã phân tích
        result = {
            "type": pivot_type,
            "price": price,
            "vn_time": vn_time,        # Giữ nguyên phút, không làm tròn
            "vn_date": vn_date,        # Format YYYY-MM-DD
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
