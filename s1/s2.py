import os
import time
from datetime import datetime, UTC
import logging
import sys
import traceback
import psutil

class S1Monitor:
    def __init__(self):
        self.s1_status = False
        self.s1_path = os.path.join(os.getcwd(), 's1.py')
        self.log_dir = 'logs/s2'
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Thiết lập logging
        self.log_file = f'{self.log_dir}/monitor_{datetime.now(UTC).strftime("%Y%m%d_%H%M%S")}.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def check_s1_status(self):
        """Kiểm tra S1 có đang chạy không"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if 'python' in proc.name().lower():
                        cmdline = ' '.join(proc.cmdline())
                        if 's1.py' in cmdline:
                            return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False
        except Exception as e:
            logging.error(f"Lỗi khi kiểm tra S1: {str(e)}")
            return False

    def check_s1_logs(self):
        """Kiểm tra log gần nhất của S1"""
        try:
            s1_log_dir = 'logs/s1'
            if not os.path.exists(s1_log_dir):
                return []

            log_files = sorted(
                [f for f in os.listdir(s1_log_dir) if f.endswith('.log')],
                key=lambda x: os.path.getctime(os.path.join(s1_log_dir, x)),
                reverse=True
            )

            if not log_files:
                return []

            latest_log = os.path.join(s1_log_dir, log_files[0])
            with open(latest_log, 'r', encoding='utf-8') as f:
                last_lines = f.readlines()[-5:]
                errors = []
                for line in last_lines:
                    if 'error' in line.lower() or 'exception' in line.lower():
                        errors.append(line.strip())
                return errors

        except Exception as e:
            logging.error(f"Lỗi khi đọc log S1: {str(e)}")
            return []

    def run_diagnostics(self):
        """Chạy chẩn đoán S1"""
        print("\n=== CHẨN ĐOÁN S1 ===")
        print(f"Thời gian: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        if not os.path.exists(self.s1_path):
            print("❌ Không tìm thấy file s1.py")
            print("→ Kiểm tra lại tên file và đường dẫn của s1.py")
            return

        s1_running = self.check_s1_status()
        print(f"Trạng thái: {'🟢 Đang chạy' if s1_running else '🔴 Đã dừng'}")

        errors = self.check_s1_logs()
        if errors:
            print("\nLỗi phát hiện trong log S1:")
            for error in errors:
                print(f"• {error}")
        else:
            print("\n✅ Không phát hiện lỗi trong log S1")

        print("\n=== KẾT THÚC CHẨN ĐOÁN ===")

    def show_menu(self):
        """Hiển thị menu"""
        print("\nMENU:")
        print("1: Chạy chẩn đoán S1")
        print("2: Thoát")
        print("(Enter để tiếp tục giám sát)")

    def monitor(self):
        """Giám sát S1"""
        print(f"\n=== S2 MONITOR STARTED ===")
        print(f"Time: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"User: {os.getlogin()}")
        print(f"S1 Path: {self.s1_path}")
        self.show_menu()

        while True:
            try:
                # Kiểm tra input từ người dùng
                choice = input().strip()
                
                if choice == "1":
                    self.run_diagnostics()
                    self.show_menu()
                elif choice == "2":
                    print("\nStopping S2 monitor...")
                    break

                # Kiểm tra trạng thái S1
                s1_running = self.check_s1_status()
                if s1_running != self.s1_status:
                    if s1_running:
                        print("\n🟢 S1 is running")
                        logging.info("S1 started")
                    else:
                        print("\n🔴 S1 is not running")
                        logging.warning("S1 stopped")
                        print("Nhập '1' để chạy chẩn đoán")
                    
                    self.s1_status = s1_running

                time.sleep(1)
                
            except KeyboardInterrupt:
                print("\nStopping S2 monitor...")
                break
            except Exception as e:
                print(f"\n⚠️ Error in S2: {str(e)}")
                logging.error(traceback.format_exc())
                time.sleep(5)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        monitor = S1Monitor()
        monitor.monitor()
    except KeyboardInterrupt:
        print("\nS2 monitor stopped")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()