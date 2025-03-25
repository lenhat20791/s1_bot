import os

def load_env_file(env_file='info.env'):
    """Đọc file .env và thiết lập biến môi trường"""
    try:
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                key, value = line.split('=', 1)
                os.environ[key] = value
        return True
    except Exception as e:
        print(f"Lỗi khi đọc file {env_file}: {e}")
        return False

if __name__ == "__main__":
    load_env_file()
    print("Đã nạp biến môi trường từ info.env")