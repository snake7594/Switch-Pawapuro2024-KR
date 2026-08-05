# -*- coding: utf-8 -*-
"""확장 없는 마이라이프 완성문장 수납 가능성 측정.
풀 후보:
  A) 슬롯 꼬리: master['exe'] 각 슬롯의 [kr_end+1, jp_len+T) — 이미 NUL로 덮어쓰는 검증된 바이트.
     단 원본 RELA addend가 꼬리 내부를 가리키면 그 앞까지로 절단(접미사 공유 보호).
  B) 죽은 조각: exe_ext(활성 5,269)의 ents가 리다이렉트되면 원본 조각 문자열 참조가 사라짐.
     그 문자열을 가리키는 '모든' RELA 참조가 우리 ents뿐이면 슬롯 전체가 빈 공간.
검증: SYMTAB st_value가 풀 안을 가리키면 제외."""
import sys, os, json, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

orig = open('main', 'rb').read()
def u32(o): return struct.unpack_from('<I', orig, o)[0]
TEXT_FO, TEXT_MO, TEXT_SZ = u32(0x10), u32(0x14), u32(0x18)
ROD_FO, ROD_MO, ROD_SZ = u32(0x20), u32(0x24), u32(0x28)
DATA_FO, DATA_MO, DATA_SZ = u32(0x30), u32(0x34), u32(0x38)
RO_DELTA = ROD_MO - ROD_FO
DYN_HI = 0x3d2551d
def va2fo(va):
    if TEXT_MO <= va < TEXT_MO+TEXT_SZ: return va-TEXT_MO+TEXT_FO
    if ROD_MO <= va < ROD_MO+ROD_SZ: return va-ROD_MO+ROD_FO
    if DATA_MO <= va < DATA_MO+DATA_SZ: return va-DATA_MO+DATA_FO
    return None

# ---- RELA 파싱 ----
MOD0_FO = TEXT_FO + u32(TEXT_FO+4)
DYN_FO = va2fo((MOD0_FO-TEXT_FO+TEXT_MO) + struct.unpack_from('<i', orig, MOD0_FO+4)[0])
DYN = {}
o = DYN_FO
while True:
    t, v = struct.unpack_from('<QQ', orig, o)
    if t == 0: break
    DYN.setdefault(t, v); o += 16
RELA_FO = va2fo(DYN[7]); CNT = DYN[8]//24
arr = np.frombuffer(orig[RELA_FO:RELA_FO+CNT*24], dtype='<u8').reshape(-1, 3)
rel = arr[arr[:, 1] == 0x403]
ra = rel[:, 2].astype(np.int64)
# 문자열영역 addend → 파일오프셋, 정렬(범위 질의용)
instr = (ra >= ROD_MO+ (DYN_HI-ROD_FO)) & (ra < ROD_MO+ROD_SZ)
addend_fo = np.sort(ra[instr] - RO_DELTA)
print(f"RELA relative {len(rel):,}, 문자열영역 addend {len(addend_fo):,}")
# SYMTAB st_value
SYMTAB = DYN.get(6); STRTAB = DYN.get(5); SYMENT = DYN.get(11, 0x18)
sym_fo = []
if SYMTAB and STRTAB:
    sfo = va2fo(SYMTAB); nsym = (STRTAB-SYMTAB)//SYMENT
    for i in range(nsym):
        sv = struct.unpack_from('<Q', orig, sfo+i*SYMENT+8)[0]
        f = va2fo(sv) if ROD_MO <= sv < ROD_MO+ROD_SZ else None
        if f and f > DYN_HI: sym_fo.append(f)
sym_fo = np.sort(np.array(sym_fo, dtype=np.int64)) if sym_fo else np.array([], dtype=np.int64)
print(f"SYMTAB 문자열영역 st_value {len(sym_fo)}")
def refs_in(lo, hi):  # (lo,hi) 반개구간 내 참조 최솟값 or None
    j = np.searchsorted(addend_fo, lo, side='left')
    r = addend_fo[j] if j < len(addend_fo) and addend_fo[j] < hi else None
    k = np.searchsorted(sym_fo, lo, side='left')
    s = sym_fo[k] if k < len(sym_fo) and sym_fo[k] < hi else None
    if r is None: return s
    if s is None: return r
    return min(r, s)

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')
def fitlen(nb, region):
    if len(nb) > region-1:
        nb = nb[:region-1]
        while nb:
            try: nb.decode('utf-8'); break
            except UnicodeDecodeError: nb = nb[:-1]
    return len(nb)

master = json.load(open('번역_마스터.json', encoding='utf-8'))

# ---- A) 슬롯 꼬리 ----
tails = []
slot_by_off = {}
for r in master['exe']:
    off = r['off']
    if off <= DYN_HI: continue
    jpb = r['jp'].encode('utf-8')
    if orig[off:off+len(jpb)] != jpb: continue
    e = off + len(jpb); T = 0
    while e+T < len(orig) and orig[e+T] == 0: T += 1
    region_end = off + len(jpb) + T
    slot_by_off[off] = (off, region_end)
    kr = fitlen(enc(r['ko']), len(jpb)+T)
    lo = off + kr + 1              # KR 종결 NUL 다음
    if lo >= region_end: continue
    p = refs_in(off+1, region_end)  # 슬롯 내부 참조(시작 제외)
    hi = region_end if (p is None or p <= lo) else min(region_end, p)
    if p is not None and lo < p < region_end: hi = p
    elif p is not None and p <= lo: continue   # 참조가 KR 내부/직후 → 꼬리 포기(보수적)
    if hi - lo >= 8: tails.append((lo, hi))

tail_total = sum(h-l for l, h in tails)
print(f"\nA) 슬롯 꼬리: {len(tails):,}개, 합계 {tail_total:,}B")

# ---- B) 죽은 조각 ----
ours = set()
for x in master['exe_ext']:
    for ep in x['ents']: ours.add(ep)
# ent → 원본 addend(조각 VA)
frag_va = {}
for ep in ours:
    frag_va[ep] = struct.unpack_from('<Q', orig, ep+16)[0]
# addend값 → 참조하는 모든 RELA ent 목록
from collections import defaultdict
want = set(frag_va.values())
ref_ents = defaultdict(list)
ro_all, ri_all, ra_all = arr[:, 0], arr[:, 1], arr[:, 2]
sel = np.isin(ra_all, np.array(list(want), dtype=np.uint64)) & (ri_all == 0x403)
for k in np.nonzero(sel)[0].tolist():
    ref_ents[int(ra_all[k])].append(RELA_FO + k*24)
dead = []
claimed = set()
for F in sorted(want):
    ents = ref_ents.get(F, [])
    if not ents or any(e not in ours for e in ents): continue   # 외부 참조 존재 → 생존
    fo = va2fo(F)
    if fo is None or fo <= DYN_HI or fo in claimed: continue
    e = orig.find(b'\x00', fo); T = 0; k = e
    while k < len(orig) and orig[k] == 0: T += 1; k += 1
    region_end = fo + (e-fo) + T
    # 내부 참조(시작 제외; 시작 참조는 전부 ours)
    p = refs_in(fo+1, region_end)
    if p is not None: region_end = p
    if region_end - fo >= 8:
        dead.append((fo, region_end)); claimed.add(fo)
dead_total = sum(h-l for l, h in dead)
print(f"B) 죽은 조각: {len(dead):,}개, 합계 {dead_total:,}B")

# ---- 겹침 제거 + 문장 수납 시뮬레이션 ----
iv = sorted(tails + dead)
merged = []
for l, h in iv:
    if merged and l < merged[-1][1]: merged[-1] = (merged[-1][0], max(merged[-1][1], h))
    else: merged.append((l, h))
pool = [(l, h) for l, h in merged]
pool_total = sum(h-l for l, h in pool)
sents = sorted({enc(x['ko']) for x in master['exe_ext']}, key=lambda b: (-len(b), b))
need = sum(len(s)+1 for s in sents)
print(f"\n풀 합계 {pool_total:,}B (청크 {len(pool):,}) vs 필요 {need:,}B (문장 {len(sents):,})")
# best-fit decreasing
import bisect


# 간단 시뮬: 큰 문장부터, 남은 용량 가장 작은 맞는 청크에
chunks = sorted([h-l for l, h in pool])
placed = 0; fail = 0
import heapq
# 다중셋 대용: 정렬 리스트

chunks_sl = sorted(chunks)
for s in sents:
    n = len(s)+1
    j = bisect.bisect_left(chunks_sl, n)
    if j < len(chunks_sl):
        c = chunks_sl.pop(j)
        left = c-n
        if left > 0: bisect.insort(chunks_sl, left)
        placed += 1
    else: fail += 1
print(f"수납 시뮬(BFD): 성공 {placed:,} / 실패 {fail:,}")
if fail:
    failed_sizes = []  # 실패 크기 대략
    print("  (실패분은 대형 문장 — 분할 배치나 추가 풀 필요)")
