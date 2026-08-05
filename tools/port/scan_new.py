# -*- coding: utf-8 -*-
"""순한자 포함 전수 신규/미번역 수색 + maxb 규약 수정 + φ 역전 점검."""
import sys, os, json, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
from port_lib import load_nso, region_strings, cache_path, P18, P15

WS = r"C:\pawa_ws_18"; OUT = r"C:\pawa_port"
A = load_nso(P18); B = load_nso(P15)
o18, o15 = A['data'], B['data']
master = json.load(open(WS + r"\번역_마스터.json", encoding='utf-8'))
m115 = json.load(open(OUT + r"\번역_마스터_115.json", encoding='utf-8'))
phi = pickle.load(open(cache_path('phi.pkl'), 'rb'))['m']

# --- φ 역전 점검 ---
ks = np.array(sorted(phi)); vs = np.array([phi[int(k)] for k in ks])
inv = np.nonzero(np.diff(vs) <= 0)[0]
print(f"φ 역전 {len(inv)}건")
for i in inv.tolist():
    a1, a2 = int(ks[i]), int(ks[i+1]); b1, b2 = int(vs[i]), int(vs[i+1])
    s1 = o18[a1:o18.find(b'\x00', a1)]; s2 = o18[a2:o18.find(b'\x00', a2)]
    print(f"  0x{a1:x}→0x{b1:x} {s1[:24]!r} / 0x{a2:x}→0x{b2:x} {s2[:24]!r}")

# --- maxb 규약 수정: len(jp)+T-1 ---
fix = 0
for r in m115['exe']:
    jpb = r['jp'].encode('utf-8')
    e = r['off'] + len(jpb); T = 0
    while o15[e+T] == 0: T += 1
    nb = len(jpb) + T - 1
    if r['maxb'] != nb: r['maxb'] = nb; fix += 1
print(f"maxb 보정 {fix:,}건 (규약 = len(jp)+후행NUL런-1)")

# --- 전수 스캔 ---
covered = set(r['off'] for r in m115['exe'])
KANA = lambda c: ('\u3040' <= c <= '\u309f') or ('\u30a1' <= c <= '\u30fa') or c in '\u30fd\u30fe'
def cjk(c): return ('\u4e00' <= c <= '\u9fff') or ('\u3400' <= c <= '\u4dbf') or ('\uf900' <= c <= '\ufaff')
def fullw(c): return '\uff01' <= c <= '\uff60'

s18, e18 = region_strings(A); L18 = e18 - s18
set18 = set()
for i in np.nonzero((L18 >= 2) & (L18 <= 4096))[0].tolist():
    set18.add(o18[s18[i]:e18[i]])

starts, ends = region_strings(B); L = ends - starts
sel = np.nonzero((L >= 2) & (L <= 4096))[0]
kana_new, kanji_new, kana_old, kanji_old = [], [], [], []
for i in sel.tolist():
    off = int(starts[i])
    if off in covered: continue
    b = o15[off:ends[i]]
    try: s = b.decode('utf-8')
    except UnicodeDecodeError: continue
    hk = any(KANA(c) for c in s)
    hc = any(cjk(c) or fullw(c) for c in s)
    if not (hk or hc): continue
    isold = b in set18
    if hk: (kana_old if isold else kana_new).append((off, s))
    else:  (kanji_old if isold else kanji_new).append((off, s))
print(f"\n미커버: 가나포함 신규 {len(kana_new):,} / 기존 {len(kana_old):,}  ·  "
      f"순한자·전각 신규 {len(kanji_new):,} / 기존 {len(kanji_old):,}")

# 순한자 신규는 오탐이 많으므로 '1.8.0 마스터에 같은 내용의 번역이 있는가' 로도 분류
by_jp = {}
for r in master['exe']: by_jp.setdefault(r['jp'], r['ko'])
auto = [(o, s) for o, s in kanji_new + kana_new if s in by_jp]
print(f"  신규 중 마스터에 동일 원문 번역이 이미 있는 것 {len(auto):,} → 자동 적용 가능")
print("\n순한자 신규 상위 25:")
for o, s in sorted(kanji_new, key=lambda x: -len(x[1]))[:25]:
    print(f"  0x{o:x} [{len(s.encode('utf-8')):4d}B] {s[:70]!r}{'  ← 마스터有' if s in by_jp else ''}")

json.dump({'kana_new': [{'off': o, 'jp': s} for o, s in kana_new],
           'kanji_new': [{'off': o, 'jp': s} for o, s in kanji_new],
           'kana_old': [{'off': o, 'jp': s} for o, s in kana_old],
           'kanji_old': [{'off': o, 'jp': s} for o, s in kanji_old]},
          open(OUT + r"\_scan115.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump(m115, open(OUT + r"\번역_마스터_115.json", 'w', encoding='utf-8'), ensure_ascii=False)
print(f"\n→ _scan115.json 저장 · 마스터 maxb 보정 저장")
