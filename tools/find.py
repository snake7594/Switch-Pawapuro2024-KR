import os

# 찾을 시그니처(16진수 → 바이트)
signature = bytes.fromhex('554E4344464F4E54')

# 현재 폴더 내 모든 파일 검색
current_dir = os.getcwd()
for filename in os.listdir(current_dir):
    filepath = os.path.join(current_dir, filename)
    if os.path.isfile(filepath):
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
                offset = 0
                found = False
                while True:
                    pos = data.find(signature, offset)
                    if pos == -1:
                        break
                    if not found:
                        print(f"\n파일명: {filename}")
                        found = True
                    print(f"  발견 위치: {pos} (0x{pos:X})")
                    offset = pos + 1
        except Exception as e:
            print(f"Error reading {filename}: {e}")
