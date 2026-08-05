# -*- coding: utf-8 -*-
"""main-safe5의 문자열영역 dangling(불완전 UTF-8 + NUL) 전역 수리 → main-safe6.
버그난 구 patch_at_offset이 남긴 매달린 선두바이트(게임이 NUL 삼켜 인접 ID/문자열까지 읽음)를
제거. 안전장치: **원본(main-원본)과 다른=주입된 문자열**에서만 수리(원본 바이너리 불건드림).
불완전 시퀀스 [i:p] (p=NUL위치)를 0으로 채워 유효 UTF-8 종료 보장."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용

SRC = "inject_out/main-safe5"
DST = "inject_out/main-safe6"
buf = bytearray(open(SRC, "rb").read())
orig = open("!exefs-작업/main-원본", "rb").read()
LO, HI = 0x3d00000, 0x5600000

fixed = 0; skipped_bin = 0
i = LO
while i < HI - 1:
    b = buf[i]
    if 0xC2 <= b <= 0xF4:
        need = 2 if b < 0xE0 else (3 if b < 0xF0 else 4)
        c = 1
        while c < need and i + c < HI and 0x80 <= buf[i + c] <= 0xBF:
            c += 1
        if c < need and i + c < HI and buf[i + c] == 0x00:
            # 불완전 시퀀스가 NUL로 끝남 → dangling 후보
            p = i + c                          # NUL 위치
            st = i
            while st > LO and buf[st - 1] != 0:
                st -= 1                          # 문자열 시작
            # 안전장치: 이 문자열이 주입됨(원본과 다름) 확인
            if bytes(buf[st:p]) != orig[st:p]:
                for k in range(i, p):
                    buf[k] = 0                   # 매달린 꼬리 제거
                fixed += 1
            else:
                skipped_bin += 1
            i = p + 1
            continue
        i += need
    else:
        i += 1

open(DST, "wb").write(buf)
print(f"dangling 수리 {fixed}건, (원본과 동일해 보호=스킵 {skipped_bin}건)")
print(f"저장 {DST} len={len(buf)}")

# 검증: 7개 ID 앞 문자열이 이제 유효 UTF-8인지
final = bytes(buf)
for ids in ['CHE_assign_player', 'PEN_shop_item_00', 'TEAMLG_OR02.CHK', 'VersusModeSelectProc']:
    x = final.find(ids.encode())
    if x < 0:
        print(f"  {ids}: 없음"); continue
    k = x - 1
    while k >= 0 and final[k] == 0:
        k -= 1
    j = final.rfind(b"\x00", 0, k + 1)
    seg = final[j + 1:k + 1]
    try:
        seg.decode("utf-8"); print(f"  {ids}: 앞문자열 유효UTF8 ✓ ({seg.decode('utf-8')[:16]!r})")
    except UnicodeDecodeError:
        print(f"  {ids}: ★여전히 깨짐 {seg[-6:].hex()}")
