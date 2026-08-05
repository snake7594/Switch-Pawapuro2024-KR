# -*- coding: utf-8 -*-
"""SEN_TEXT.CHK(선수 소개문) 수리: 배포 슬롯 손상 → 원본 body 재구성+완역(tsv) 재주입 → RES10 끝 재배치.
- 원본(root RES10)의 정상 슬롯에서 body 획득
- JSON의 SEN_TEXT scan 번역 전량을 patch_at_offset(슬랙)으로 주입 — **tsv 인코딩**(폰트 단일화 이후 표준)
- repack_out/RES10.RDB 끝(섹터정렬)에 자족 슬롯 기록, repack_out RDI(OFFSET/DEC_SIZE) 갱신
- 재독 검증(복호·해제·한국어 표본)"""
import os, sys, struct, zlib, json
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib
from rdblib import crypt_fast, file_key, align_up, SECTOR, locate
import inject_lib as L

ENC = L.Encoder(os.path.join("!exefs-작업", "hangul_to_hanja.tsv"))
FN = 'SEN_TEXT.CHK'

# 1) 원본 body
ORG = rdblib.RDB('.')
body = bytearray(ORG.read_body(FN))
ORG.close()
orig_len = len(body)
print(f"원본 body {orig_len}B")

# 2) 번역 주입(tsv)
doc = json.load(open("번역_일본어.json", encoding="utf-8"))
pairs = []
for s in doc["strings"]:
    ko = str(s.get("ko", "")).strip()
    if not ko: continue
    for o in s["occurrences"]:
        if o["method"] == "scan" and o.get("file") == FN:
            pairs.append((s["jp"].encode("utf-8"), ENC.encode(ko)))
pairs = list(dict.fromkeys(pairs))
hit = trunc = 0
for jpb, kob in pairs:
    jl = len(jpb); st = 0
    while True:
        i = body.find(jpb, st)
        if i < 0: break
        pre = (i == 0) or (body[i-1] == 0)
        post = (i + jl >= len(body)) or (body[i+jl] == 0)
        if pre and post:
            if L.patch_at_offset(body, i, jl, kob): trunc += 1
            hit += 1
        st = i + 1
assert len(body) == orig_len
print(f"소개문 주입: 치환 {hit} (사전 {len(pairs)}건), 잘림 {trunc}")

# 3) 재배치 기록(repack_out RES10 끝)
DEP = rdblib.RDB('repack_out', writable=True)
ent = DEP.idx[FN]
loc = locate(ent["stored"], ent["flag"])
rdbn, off0, is10 = loc
key = file_key(FN)
# 권위 헤더: 원본 root의 정상 헤더 사용
with open(rdbn, "rb") as f:
    f.seek(locate(rdblib.RDB('.').idx[FN]["stored"], 0x20)[1]); pass
O2 = rdblib.RDB('.')
l2 = locate(O2.idx[FN]["stored"], O2.idx[FN]["flag"])
f2 = O2.f[l2[0]]; f2.seek(l2[1])
hdr = bytearray(crypt_fast(f2.read(32), key))
O2.close()
comp = zlib.compress(bytes(body), 9)
new_decsize = align_up(len(body), 4)
outpath = os.path.join('repack_out', 'RES10.RDB')
new_local = align_up(os.path.getsize(outpath), SECTOR)
new_stored = new_local // SECTOR + 0x1000000
struct.pack_into("<I", hdr, 0x18, len(comp))
struct.pack_into("<I", hdr, 0x1C, new_local // SECTOR)
phys = align_up(max(new_decsize, 32 + len(comp)), SECTOR)
blob = bytearray(phys); blob[:32] = hdr; blob[32:32+len(comp)] = comp
f = DEP.f['RES10.RDB']
f.seek(new_local); f.write(crypt_fast(bytes(blob), key)); f.flush()
struct.pack_into("<I", DEP.dec, ent["rec_off"], new_stored)
struct.pack_into("<I", DEP.dec, ent["rec_off"]+4, new_decsize)
enc = crypt_fast(bytes(DEP.dec), rdblib.RDI_KEY)
open(os.path.join('repack_out', 'RES00.RDI'), 'wb').write(enc)
print(f"재배치: RES10 0x{new_local:x} (stored 0x{new_stored:x}), comp {len(comp)}B, RDI 갱신")
DEP.close()

# 4) 재독 검증
V = rdblib.RDB('repack_out')
nb = V.read_body(FN)
V.close()
def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
tsv_r = {v: k for k, v in load_tsv().items()}
smp = []
pos = 0
while pos < len(nb) and len(smp) < 5:
    e = nb.find(b'\x00', pos)
    if e < 0: break
    if 20 <= e - pos <= 200:
        try:
            s = ''.join(tsv_r.get(c, c) for c in nb[pos:e].decode('utf-8'))
            if sum(1 for c in s if '가' <= c <= '힣') > 8: smp.append(s[:44])
        except UnicodeDecodeError: pass
    pos = e + 1
print("재독 OK", len(nb), "B; 소개문 표본:")
for s in smp: print("  ", s)
