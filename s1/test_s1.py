import pytest
from s1 import S1Bot

@pytest.fixture
def bot():
    """Khởi tạo bot trước khi chạy test"""
    return S1Bot()

def test_s1bot_initialization(bot):
    """Kiểm tra xem bot có được khởi tạo không"""
    assert bot is not None

def test_find_pivots(bot):
    """Kiểm tra hàm tìm điểm pivot"""
    prices = [100, 105, 102, 98, 101, 107, 103]
    times = [
        "2025-03-16 10:00:00", "2025-03-16 10:05:00", "2025-03-16 10:10:00",
        "2025-03-16 10:15:00", "2025-03-16 10:20:00", "2025-03-16 10:25:00", "2025-03-16 10:30:00"
    ]
    
    pivots = bot.find_pivots(prices, times, tolerance=0.0001)
    
    assert isinstance(pivots, list), "find_pivots phải trả về danh sách"
    assert len(pivots) > 0, "Không tìm thấy pivot nào"
    assert any(p[0] == "HH" for p in pivots), "Không tìm thấy HH nào"
    assert any(p[0] == "LL" for p in pivots), "Không tìm thấy LL nào"

def test_analyze_patterns(bot):
    """Kiểm tra phân tích mẫu hình"""
    price = 100.0
    timestamp = "2025-03-16 10:00:00"
    patterns = bot.btc_analyzer.analyze(price, timestamp)
    
    assert isinstance(patterns, list), "Kết quả phân tích mẫu hình phải là danh sách"

def test_send_alert_once(bot):
    """Kiểm tra logic gửi cảnh báo một lần"""
    bot.last_pattern = "Mẫu hình giảm"
    
    new_patterns = ["Mẫu hình giảm"]
    assert bot.should_send_alert(new_patterns) == False, "Bot không nên gửi cảnh báo trùng lặp"

    new_patterns = ["Mẫu hình tăng"]
    assert bot.should_send_alert(new_patterns) == True, "Bot nên gửi cảnh báo khi có mẫu hình mới"

if __name__ == "__main__":
    pytest.main()
