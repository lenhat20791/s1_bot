def add_price_data(self, data):
    """Thêm dữ liệu giá mới với logging chi tiết"""
    try:
        # Cập nhật thời gian và log header
        self.current_time = data["time"]
        save_log("\n" + "="*50, DEBUG_LOG_FILE)
        save_log(f"⏰ Thời điểm: {self.current_time}", DEBUG_LOG_FILE)
        save_log(f"📊 Dữ liệu giá:", DEBUG_LOG_FILE)
        save_log(f"  - High: ${data['high']:,.2f}", DEBUG_LOG_FILE)
        save_log(f"  - Low: ${data['low']:,.2f}", DEBUG_LOG_FILE)
        save_log(f"  - Close: ${data['price']:,.2f}", DEBUG_LOG_FILE)

        # Thêm vào lịch sử giá
        self.price_history.append(data)
        if len(self.price_history) > (self.LEFT_BARS + self.RIGHT_BARS + 1):
            self.price_history.pop(0)
        
        save_log(f"📈 Số nến trong lịch sử: {len(self.price_history)}/{self.LEFT_BARS + self.RIGHT_BARS + 1}", DEBUG_LOG_FILE)

        # Phát hiện pivot mới
        save_log("\n🔍 Kiểm tra High Pivot:", DEBUG_LOG_FILE)
        high_pivot = self.detect_pivot(data["high"], "high")
        if high_pivot:
            self.stats['total_detected'] += 1
            
        save_log("\n🔍 Kiểm tra Low Pivot:", DEBUG_LOG_FILE)
        low_pivot = self.detect_pivot(data["low"], "low")
        if low_pivot:
            self.stats['total_detected'] += 1

        save_log("="*50 + "\n", DEBUG_LOG_FILE)
        return True

    except Exception as e:
        save_log(f"❌ Lỗi khi thêm price data: {str(e)}", DEBUG_LOG_FILE)
        return False
