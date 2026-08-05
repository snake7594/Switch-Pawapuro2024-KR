# -*- coding: utf-8 -*-
"""마이라이프 대사 리다이렉트 주입 → main-mylife.
- 대상: 마이라이프_대사.json의 2조각+ 문장(1조각은 기존 제자리 번역 유지)
- 방법: 안전 죽은풀(참조없는 zero-run)에 문장 ko(tsv) 기록 → 각 문장 frags[0].ent_fpos+16=문장VA, frags[1:]=빈문자열VA
- 조각 문자열 불변, 동적영역은 리다이렉트 엔트리 addend(+16)만 변경(정렬됨=안전)
- 베이스: inject_out/main-new (통합마스터 최신)"""
import sys, os, json, struct
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

BASE = 'inject_out/main-new'
OUT = 'inject_out/main-mylife'
orig = open('main', 'rb').read()
buf = bytearray(open(BASE, 'rb').read())
RO_FO, RO_MO = 0x2aafb21, 0x2ab0000
DELTA = RO_MO - RO_FO
def fo2va(fo): return fo + DELTA
DYN_HI = 0x3d2551d
import struct as _s
def u32(o): return _s.unpack_from('<I', orig, o)[0]
DATA_FO = u32(0x30); TEXT_FO, TEXT_MO, TEXT_SZ = u32(0x10), u32(0x14), u32(0x18)

# ---- 안전 죽은풀 수집(참조 없는 zero-run) ----
a = np.frombuffer(bytes(buf), dtype=np.uint8); b = np.frombuffer(orig, dtype=np.uint8)
both0 = (a == 0) & (b == 0); both0[:DYN_HI] = False; both0[DATA_FO:] = False
idx = np.nonzero(both0)[0]
brk = np.nonzero(np.diff(idx) > 1)[0]
rs = idx[np.concatenate([[0], brk+1])]; re_ = idx[np.concatenate([brk, [len(idx)-1]])]
runs = [(int(s), int(e)) for s, e in zip(rs, re_) if e-s+1 >= 64]
# 위험 VA(RELA addend + data 포인터 + ADRP 페이지)
F, M = RO_FO, RO_MO
RELA_F = 0x2ab0058 - M + F; RELA_CNT = 0xc36e2
rela = np.frombuffer(orig[RELA_F:RELA_F+RELA_CNT*24], dtype='<u8').reshape(-1, 3)
adds = rela[:, 2]
lo, hi = fo2va(DYN_HI), fo2va(DATA_FO)
danger = set(int(x) for x in np.unique(adds[(adds >= lo) & (adds < hi)]))
data = orig[DATA_FO:DATA_FO+u32(0x38)]
dp = np.frombuffer(data[:len(data)//8*8], dtype='<u8')
danger |= set(int(x) for x in dp[(dp >= lo) & (dp < hi)])
text = orig[TEXT_FO:TEXT_FO+TEXT_SZ]; tw = np.frombuffer(text[:len(text)//4*4], dtype='<u4')
ai = np.nonzero((tw & 0x9f000000) == 0x90000000)[0]
w = tw[ai].astype(np.int64); immlo = (w >> 29) & 3; immhi = (w >> 5) & 0x7ffff
imm = (immhi << 2) | immlo; imm = np.where(imm & (1 << 20), imm - (1 << 21), imm)
pg = ((TEXT_MO + ai*4) & ~0xfff) + imm*0x1000
dpages = set(int(x) for x in np.unique(pg[(pg >= lo) & (pg < hi)]))
dva = np.array(sorted(danger), dtype=np.int64)
safe_pools = []
for s, e in runs:
    vs, ve = fo2va(s+32), fo2va(e-32)
    if ve <= vs: continue
    if any(p >= (vs & ~0xfff) and p <= ve for p in dpages): continue
    k = np.searchsorted(dva, vs)
    if k < len(dva) and dva[k] < ve: continue
    safe_pools.append([s+32, e-32])   # 파일오프셋 [start, end)
safe_pools.sort(key=lambda p: -(p[1]-p[0]))   # 큰 조각 우선(파편화 최소)
safe_total = sum(e-s for s, e in safe_pools)
print(f"안전 죽은풀 {len(safe_pools)}개, {safe_total//1024}KB (최대 {(safe_pools[0][1]-safe_pools[0][0])//1024}KB)")

# ---- 문장 수집 + dedup ----
d = json.load(open('마이라이프_대사.json', encoding='utf-8'))
sents = []
for sc in d['scenes']:
    for s in sc['sentences']:
        if s['n_frag'] >= 2 and s['ko']:
            sents.append(s)
# 고유 인코딩 문자열(dedup)
import bisect
uniq = {}   # eb -> None(placeholder)
for s in sents: uniq[enc(s['ko'])] = None
# 빈문자열 1바이트를 가장 작은 조각에서
# best-fit decreasing: 조각을 [free, start] 로, 문장 큰 것부터 들어갈 최소 조각
free_pools = sorted(([e-s, s] for s, e in safe_pools))   # (free, start) 오름차순
def alloc(nbytes):
    # free >= nbytes 인 최소 조각
    k = bisect.bisect_left(free_pools, [nbytes, -1])
    if k >= len(free_pools): return None
    free, st = free_pools.pop(k)
    off = st
    nf = free - nbytes
    if nf > 0: bisect.insort(free_pools, [nf, st + nbytes])
    return off
empty_fo = alloc(1); buf[empty_fo] = 0; empty_va = fo2va(empty_fo)
stats = dict(sent=0, reused=0, redir=0, empt=0, trunc=0, nopool=0)
enc_map = {}
for eb in sorted(uniq, key=lambda x: -len(x)):   # 큰 문장 먼저
    fo = alloc(len(eb)+1)
    if fo is None: continue
    buf[fo:fo+len(eb)] = eb; buf[fo+len(eb)] = 0
    enc_map[eb] = fo2va(fo)
for s in sents:
    eb = enc(s['ko'])
    va = enc_map.get(eb)
    if va is None: stats['nopool'] += 1; continue
    fr = s['frags']
    if fr[0]['ent_fpos'] is None: continue
    struct.pack_into('<Q', buf, fr[0]['ent_fpos']+16, va); stats['redir'] += 1
    for f in fr[1:]:
        if f['ent_fpos'] is None: continue
        struct.pack_into('<Q', buf, f['ent_fpos']+16, empty_va); stats['empt'] += 1
    stats['sent'] += 1
# ---- 검증: 동적영역 변경 = 리다이렉트 엔트리 addend만 ----
c = np.frombuffer(bytes(buf), dtype=np.uint8)
base = np.frombuffer(open(BASE, 'rb').read(), dtype=np.uint8)
diff = np.nonzero(c[:DYN_HI] != base[:DYN_HI])[0]
# 허용: 각 리다이렉트 엔트리 +16..+24
allowed = set()
for s in sents:
    for f in s['frags']:
        if f['ent_fpos'] is not None:
            for j in range(16, 24): allowed.add(f['ent_fpos']+j)
bad = [int(x) for x in diff if int(x) not in allowed]
assert not bad, f"동적영역 예상외 변경 {len(bad)}: {bad[:5]}"
open(OUT, 'wb').write(bytes(buf))
import hashlib
print(f"주입 {stats}")
print(f"동적영역 변경 {len(diff)}B = 리다이렉트 addend만 OK")
print(f"→ {OUT}  md5 {hashlib.md5(bytes(buf)).hexdigest()}")
