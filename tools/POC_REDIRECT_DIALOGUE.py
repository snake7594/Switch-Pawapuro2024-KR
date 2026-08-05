# -*- coding: utf-8 -*-
"""PoC: 조각 조합 대사를 전체 문장 하나로 리다이렉트.
대상: "今日は待ちに待った入団会見。" (8조각) → "오늘은 기다리고 기다리던 입단회견。"
방법: .rodata 죽은공간(원본·배포본 둘 다 0인 zero-run)에 전체 한글대사 기록 →
      첫 RELA 엔트리 addend를 그 VA로, 나머지 7개를 빈문자열 VA로 치환.
베이스: 현재 배포본 main-new. 동적재배치 엔트리는 정렬돼 있어 addend(+16) 8B 교체는 안전."""
import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')

orig = open('main', 'rb').read()
buf = bytearray(open('inject_out/main-new', 'rb').read())
RO_FO, RO_MO = 0x2aafb21, 0x2ab0000
DELTA = RO_MO - RO_FO          # fileoff → VA
DYN = (0x2aafb79, 0x3d2551d)
def fo2va(fo): return fo + DELTA

# --- 이 대사의 8 엔트리 파일위치 ---
F, M = RO_FO, RO_MO
RELA_F = 0x2ab0058 - M + F; RELA_CNT = 0xc36e2
rela = np.frombuffer(orig[RELA_F:RELA_F+RELA_CNT*24], dtype='<u8').reshape(-1, 3)
i0 = int(np.nonzero(rela[:, 0] == 0x5dc8518)[0][0])
ent_fpos = [RELA_F + 24*(i0+k) for k in range(8)]
# 확인
for k, fp in enumerate(ent_fpos):
    roff, rinfo, radd = struct.unpack_from('<QQQ', buf, fp)
    assert rinfo == 0x403 and roff == 0x5dc8518 + 8*k, f"엔트리{k} 불일치"
print("8 엔트리 파일위치 확인 OK")

# --- 죽은공간(zero-run) 찾기: 문자열영역(>DYN_HI)에서 원본·배포본 둘 다 0인 런 ---
a = np.frombuffer(bytes(buf), dtype=np.uint8); b = np.frombuffer(orig, dtype=np.uint8)
region_start = DYN[1] + 0x100
seg = (a[region_start:] == 0) & (b[region_start:] == 0)
# 연속 0런 찾기(≥256B, 32정렬 여유)
need = 256
run_start = None; cnt = 0; pool_fo = None
for i in range(len(seg)):
    if seg[i]:
        if cnt == 0: run_start = i
        cnt += 1
        if cnt >= need:
            pool_fo = region_start + run_start + 32   # 앞 32B 예약
            break
    else:
        cnt = 0
assert pool_fo is not None, "죽은공간 없음"
pool_fo = (pool_fo + 7) & ~7   # 8정렬
print(f"죽은공간 풀 @ {hex(pool_fo)} (VA {hex(fo2va(pool_fo))})")

# --- 전체대사 기록 ---
line = "오늘은 기다리고 기다리던 입단회견。"
lb = enc(line)
buf[pool_fo:pool_fo+len(lb)] = lb
buf[pool_fo+len(lb)] = 0                      # 대사 종료 NUL
empty_fo = pool_fo + len(lb) + 1
buf[empty_fo] = 0                              # 빈문자열(즉시 NUL)
line_va = fo2va(pool_fo)
empty_va = fo2va(empty_fo)
print(f"대사 VA {hex(line_va)} ({len(lb)}B), 빈문자열 VA {hex(empty_va)}")

# --- 엔트리 addend 치환 ---
struct.pack_into('<Q', buf, ent_fpos[0] + 16, line_va)     # 엔트리0 = 전체대사
for k in range(1, 8):
    struct.pack_into('<Q', buf, ent_fpos[k] + 16, empty_va)  # 나머지 = 빈문자열
print("엔트리 addend 치환 완료 (0=대사, 1~7=빈문자열)")

# --- 검증: 동적영역(구조) 불변 except 이 8 엔트리 addend ---
c = np.frombuffer(bytes(buf), dtype=np.uint8)
base = np.frombuffer(open('inject_out/main-new', 'rb').read(), dtype=np.uint8)
diff = np.nonzero(c[:DYN[1]] != base[:DYN[1]])[0]
allowed = set()
for fp in ent_fpos:
    for j in range(16, 24): allowed.add(fp + j)
bad = [int(x) for x in diff if int(x) not in allowed]
assert not bad, f"동적영역 예상외 변경 {bad[:5]}"
print(f"동적영역 변경 = 8엔트리 addend만 ({len(diff)}B) OK")

open('inject_out/main-poc', 'wb').write(bytes(buf))
import hashlib
print(f"→ inject_out/main-poc  md5 {hashlib.md5(bytes(buf)).hexdigest()}")
