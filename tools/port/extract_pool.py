# -*- coding: utf-8 -*-
"""safe28 의 풀 리다이렉트에서 (원문 문자열 → 전체 한국어) 를 추출해 1.15.0 오프셋에 붙인다."""
import sys, os, json, struct, pickle
from collections import defaultdict, Counter
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
from port_lib import load_nso, cache_path, P18, P15

WS = r"C:\pawa_ws_18"; OUT = r"C:\pawa_port"
A = load_nso(P18); B = load_nso(P15)
o18 = A['data']; o15 = B['data']
s28 = open(WS + r"\inject_out\main-safe28", 'rb').read()
phi = pickle.load(open(cache_path('phi.pkl'), 'rb'))['m']

ro_fo, ro_mo, ro_sz = A['ROD_FO'], A['ROD_MO'], A['ROD_SZ']
da_fo, da_sz = A['DATA_FO'], A['DATA_SZ']
ro_lo, ro_hi = ro_mo, ro_mo + ro_sz
RD = A['RO_DELTA']

TSV = {}
for ln in open(WS + r"\!exefs-작업\hangul_to_hanja.tsv", encoding='utf-8-sig').read().splitlines():
    x = ln.split('\t')
    if len(x) >= 2 and x[0] and x[1]: TSV[x[0]] = x[1][0]
TSVR = {v: k for k, v in TSV.items()}
def dec(b):
    try: return ''.join(TSVR.get(c, c) for c in b.decode('utf-8'))
    except UnicodeDecodeError: return None

ao = np.frombuffer(o18, dtype=np.uint8)
pairs = []
for seg_fo, seg_sz in ((ro_fo, ro_sz), (da_fo, da_sz)):
    n = seg_sz // 8
    a1 = np.frombuffer(o18[seg_fo:seg_fo+n*8], dtype='<u8')
    a2 = np.frombuffer(s28[seg_fo:seg_fo+n*8], dtype='<u8')
    ch = np.nonzero((a1 != a2) & (a1 >= ro_lo) & (a1 < ro_hi) & (a2 >= ro_lo) & (a2 < ro_hi))[0]
    for i in ch.tolist():
        pairs.append((seg_fo + i*8, int(a1[i]), int(a2[i])))
print(f"포인터 변경(양쪽 다 rodata VA) {len(pairs):,}")

bysrc = defaultdict(set)
skip = Counter()
for loc, old, new in pairs:
    sfo, nfo = old - RD, new - RD
    if not (A['DYN_HI'] < sfo < A['STR_END']): skip['src범위'] += 1; continue
    e = s28.find(b'\x00', nfo)
    kb = s28[nfo:e]
    if len(kb) == 0: skip['빈문자열'] += 1; continue
    if ao[nfo:nfo+len(kb)].max() != 0: skip['풀아님'] += 1; continue   # 원본이 NUL 이던 자리만
    ko = dec(kb)
    if ko is None: skip['디코드실패'] += 1; continue
    bysrc[sfo].add(ko)
print(f"소스 문자열 {len(bysrc):,} · 제외 {dict(skip)}")
multi = sum(1 for v in bysrc.values() if len(v) > 1)
print(f"  한 소스에 서로 다른 번역이 붙은 경우 {multi:,}")

# 1.15.0 오프셋으로 이식
m115 = json.load(open(OUT + r"\번역_마스터_115.json", encoding='utf-8'))
off15 = set(r['off'] for r in m115['exe'])
pool = []
st = Counter()
for sfo, kos in bysrc.items():
    ko = sorted(kos, key=lambda s: (-len(s), s))[0]
    n = phi.get(sfo)
    if n is None: st['φ없음'] += 1; continue
    if n not in off15: st['마스터밖'] += 1; continue
    jp = o18[sfo:o18.find(b'\x00', sfo)]
    if o15[n:n+len(jp)] != jp: st['내용불일치'] += 1; continue
    pool.append({'off': n, 'ko': ko})
    st['ok'] += 1
print(f"이식: {dict(st)}")
pool.sort(key=lambda r: r['off'])

# 마스터의 제자리 ko 와 비교 — 풀 텍스트가 더 긴가
byoff = {r['off']: r for r in m115['exe']}
longer = same = shorter = 0
for p in pool:
    m = byoff[p['off']]
    if len(p['ko']) > len(m['ko']): longer += 1
    elif len(p['ko']) == len(m['ko']): same += 1
    else: shorter += 1
print(f"풀텍스트 vs 제자리 ko: 더김 {longer:,} · 동일 {same:,} · 더짧음 {shorter:,}")
print("샘플:")
for p in pool[:6]:
    print(f"  0x{p['off']:x}\n    제자리 {byoff[p['off']]['ko'][:60]!r}\n    풀     {p['ko'][:80]!r}")

m115['exe_pool'] = pool
json.dump(m115, open(OUT + r"\번역_마스터_115.json", 'w', encoding='utf-8'), ensure_ascii=False)
print(f"\n→ exe_pool {len(pool):,}건 마스터에 추가")
