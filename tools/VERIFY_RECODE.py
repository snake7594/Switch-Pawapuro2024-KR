# -*- coding: utf-8 -*-
"""PASS2 후 검증:
 1) COMMON_2D 폰트 본문 == _build/COMMON_2D_TSV.CHK
 2) SEN_MAIN 선수명: tsv 디코드로 한국어 복원(아리하라/모이넬로 등)
 3) 무작위 패치 슬롯 50 + 무작위 전체 슬롯 200 복호·해제 무결성
 4) 재인코딩 표본: TEXT_HSIMSCH/NXSUR 라벨 tsv 디코드"""
import sys, os, json, hashlib, random
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r"C:\Users\Jae Ho Lee\Desktop\z\실황2024")
import rdblib

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv(); TSV_R = {v: k for k, v in TSV.items()}
def dec(b):
    try: s = b.decode('utf-8')
    except UnicodeDecodeError: return None
    return ''.join(TSV_R.get(c, c) for c in s)

R = rdblib.RDB('repack_out')

# 1) 폰트
fb = R.read_body('COMMON_2D.CHK')
want = open('_build/COMMON_2D_TSV.CHK', 'rb').read()[32:]
print('1) 폰트 교체:', 'OK' if hashlib.md5(fb).digest() == hashlib.md5(want).digest() else '★불일치')

# 2) SEN_MAIN 이름 표본
b = R.read_body('SEN_MAIN.CHK')
names_found = []
# NUL 경계 문자열 중 tsv 디코드시 한글 2+ 인 것 표본
pos = 0
while pos < len(b) and len(names_found) < 12:
    e = b.find(b'\x00', pos)
    if e < 0: break
    if 6 <= e - pos <= 40:
        d = dec(b[pos:e])
        if d and sum(1 for c in d if '가' <= c <= '힣') >= 2:
            names_found.append(d)
    pos = e + 1
print('2) SEN_MAIN 문자열 표본(tsv 디코드):', names_found[:12])

# 3) 무결성
plans = json.load(open('_recode_plan.json', encoding='utf-8'))
extra = json.load(open('_sweep_patches.json', encoding='utf-8'))
allp = set(plans) | set(extra) | {'COMMON_2D.CHK'}
ok = ng = 0
for name in random.Random(3).sample(sorted(allp & set(R.idx)), min(50, len(allp))):
    try:
        x = R.read_body(name); ok += (x is not None and len(x) > 0)
    except Exception:
        ng += 1
allnames = [t['name'] for t in R.table if t['flag'] in (0, 0x20)]
for name in random.Random(4).sample(allnames, 200):
    try:
        x = R.read_body(name)
        if x is None: continue
        ok += 1
    except Exception:
        ng += 1; print('  [NG]', name)
print(f'3) 무결성: OK {ok}, NG {ng}')

# 4) TEXT_HSIMSCH 표본
b = R.read_body('TEXT_HSIMSCH.CHK')
smp = []
pos = 0
while pos < len(b) and len(smp) < 8:
    e = b.find(b'\x00', pos)
    if e < 0: break
    if 6 <= e - pos <= 30:
        d = dec(b[pos:e])
        if d and sum(1 for c in d if '가' <= c <= '힣') >= 2: smp.append(d)
    pos = e + 1
print('4) TEXT_HSIMSCH 표본:', smp)
R.close()
