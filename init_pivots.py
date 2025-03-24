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
    Phân tích cú pháp đầu vào để tạo pivot
    Format hỗ trợ:
    1. type:price:time - ví dụ: LL:83597:06:30
    2. type:price:date:time - ví dụ: 
       - LL:83597:24-03-2025:06:30 (DD-MM-YYYY)
       - LL:83597:2025-03-24:06:30 (YYYY-MM-DD)
    """
    try:
        print(f"DEBUG - Input text: {pivot_text}")
        # Loại bỏ khoảng trắng và 'h' trong thời gian nếu có
        cleaned_text = pivot_text.strip().replace('h', ':')
        parts = cleaned_text.split(":")
        
        print(f"DEBUG - Các phần sau khi tách: {parts}")
        
        # Validate số lượng phần tử
        if len(parts) not in [3, 4]:
            print(f"DEBUG - Số phần tử không hợp lệ: {len(parts)} (cần 3 hoặc 4)")
            return None
            
        # Validate và chuyển đổi loại pivot
        pivot_type = parts[0].upper()
        valid_types = ["LL", "LH", "HL", "HH"]
        if pivot_type not in valid_types:
            print(f"DEBUG - Loại pivot không hợp lệ: {pivot_type}")
            return None
            
        # Validate và chuyển đổi giá
        try:
            price = float(parts[1])
            if price <= 0:
                print(f"DEBUG - Giá không hợp lệ: {price}")
                return None
        except ValueError:
            print(f"DEBUG - Không thể chuyển đổi giá: {parts[1]}")
            return None
            
        # Xử lý ngày tháng và thời gian
        now = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
        
        if len(parts) == 3:
            # Format: type:price:time
            time_str = parts[2]
            vn_date = now.strftime('%Y-%m-%d')
            print(f"DEBUG - Format ngắn, sử dụng ngày hiện tại: {vn_date}")
        else:
            # Format: type:price:date:time
            date_str = parts[2].replace('/', '-')
            time_str = parts[3]
            
            try:
                date_parts = date_str.split('-')
                if len(date_parts) != 3:
                    print(f"DEBUG - Định dạng ngày không hợp lệ: {date_str}")
                    return None

                # Xử lý cả hai định dạng YYYY-MM-DD và DD-MM-YYYY
                if len(date_parts[0]) == 4:  # YYYY-MM-DD
                    year = int(date_parts[0])
                    month = int(date_parts[1])
                    day = int(date_parts[2])
                else:  # DD-MM-YYYY
                    year = int(date_parts[2])
                    month = int(date_parts[1])
                    day = int(date_parts[0])
                
                # Validate ngày tháng
                if not (2020 <= year <= 2030):
                    print(f"DEBUG - Năm không hợp lệ: {year}")
                    return None
                if not (1 <= month <= 12):
                    print(f"DEBUG - Tháng không hợp lệ: {month}")
                    return None
                if not (1 <= day <= 31):
                    print(f"DEBUG - Ngày không hợp lệ: {day}")
                    return None
                    
                # Format lại theo chuẩn YYYY-MM-DD
                vn_date = f"{year:04d}-{month:02d}-{day:02d}"
                print(f"DEBUG - Ngày đã xử lý: {vn_date}")
                
            except Exception as e:
                print(f"DEBUG - Lỗi xử lý ngày tháng: {str(e)}")
                print(traceback.format_exc())
                return None
            
        # Xử lý và validate thời gian
        try:
            # Xử lý định dạng thời gian HH:MM
            if ':' in time_str:
                hour, minute = map(int, time_str.split(':'))
            elif len(time_str) == 4:  # HHMM
                hour = int(time_str[:2])
                minute = int(time_str[2:])
            else:
                print(f"DEBUG - Định dạng thời gian không hợp lệ: {time_str}")
                return None
                
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                print(f"DEBUG - Thời gian không hợp lệ: {hour}:{minute}")
                return None
                
            vn_time = f"{hour:02d}:{minute:02d}"
            print(f"DEBUG - Thời gian đã xử lý: {vn_time}")
            
        except ValueError as e:
            print(f"DEBUG - Không thể xử lý thời gian: {time_str}, lỗi: {str(e)}")
            return None
            
        # Xác định direction
        direction = "high" if pivot_type in ["HH", "LH"] else "low"
        
        # Tạo và trả về kết quả
        result = {
            "type": pivot_type,
            "price": price,
            "vn_time": vn_time,
            "vn_date": vn_date,
            "direction": direction,
            "confirmed": True,
            "original_time": time_str,
            "debug_info": {
                "input": pivot_text,
                "cleaned_input": cleaned_text,
                "parts": parts,
                "parsed_hour": hour,
                "parsed_minute": minute,
                "parsed_date": vn_date
            }
        }
        
        print(f"DEBUG - Kết quả cuối cùng: {json.dumps(result, indent=2)}")
        return result
        
    except Exception as e:
        print(f"DEBUG - Lỗi không xử lý được: {str(e)}")
        print(traceback.format_exc())
        return None
