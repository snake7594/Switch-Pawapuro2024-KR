# -*- coding: utf-8 -*-
"""바뀐 7개 *_2ND CHK: 사전(원문→번역) 기반 전수 재매핑."""
import sys, os, json
from collections import defaultdict, Counter
sys.path.insert(0, r"C:\Users\Jay\Desktop\z\파워풀2024-2025\Switch-Pawapuro2024-KR\tools")
sys.stdout.reconfigure(encoding='utf-8')
from rdblib import RDB

BB = r"C:\Users\Jay\Desktop\z\파워풀2024-2025"
D18 = BB + r"\추출원본-1.8.0\romfs\cdvdroot"
D15 = BB + r"\추출원본-1.15.0\romfs\cdvdroot"
OUT = r"C:\pawa_port"
REPO = BB + r"\Switch-Pawapuro2024-KR"
CHANGED = json.load(open(OUT + r"\_rdb_diff.json", encoding='utf-8'))['diff']

orig_master = json.load(open(REPO + r"\data\번역_마스터.json", encoding='utf-8'))
m115 = json.load(open(OUT + r"\번역_마스터_115.json", encoding='utf-8'))

# --- 사전 구축: SEN_* 계열 전체 + 같은 파일 우선 ---
glob = defaultdict(Counter); perfile = defaultdict(dict)
for r in orig_master['rdb']:
    glob[r['jp']][r['ko']] += 1
    perfile[r['file']].setdefault(r['jp'], r['ko'])
conflict = sum(1 for k, v in glob.items() if len(v) > 1)
print(f"사전: 고유 원문 {len(glob):,} · 번역이 갈리는 원문 {conflict:,}")
DICT = {k: v.most_common(1)[0][0] for k, v in glob.items()}

R18 = RDB(D18); R15 = RDB(D15)
def strings(body):
    out = []; i = 0; n = len(body)
    while i < n:
        if body[i] == 0: i += 1; continue
        e = body.find(b'\x00', i)
        if e < 0: e = n
        out.append((i, body[i:e])); i = e + 1
    return out

KANA = lambda c: ('\u3040' <= c <= '\u309f') or ('\u30a1' <= c <= '\u30fa') or c in '\u30fd\u30fe'
def cjk(c): return ('\u4e00' <= c <= '\u9fff') or ('\u3400' <= c <= '\u4dbf') or ('\uf900' <= c <= '\ufaff')
def fullw(c): return '\uff01' <= c <= '\uff60'

new_rdb = [r for r in m115['rdb'] if r['file'] not in CHANGED]
untr = []
for fn in CHANGED:
    b15 = R15.read_body(fn)
    pf = perfile.get(fn, {})
    ok = new = 0
    for off, s in strings(b15):
        try: t = s.decode('utf-8')
        except UnicodeDecodeError: continue
        if not any(KANA(c) or cjk(c) or fullw(c) for c in t): continue
        ko = pf.get(t) or DICT.get(t)
        oe = off + len(s); T = 0; k = oe
        while k < len(b15) and b15[k] == 0: T += 1; k += 1
        if ko is None:
            untr.append({'file': fn, 'off': off, 'jp': t, 'maxb': len(s) + T - 1}); new += 1
            continue
        new_rdb.append({'file': fn, 'off': off, 'jp': t, 'ko': ko, 'maxb': len(s) + T - 1})
        ok += 1
    print(f"{fn:20s} 사전적용 {ok:5,} · 미번역 {new:4,}")
R18.close(); R15.close()

print(f"\nrdb 총 {len(new_rdb):,} (1.8.0 마스터 {len(orig_master['rdb']):,}) · 미번역 {len(untr):,}")
m115['rdb'] = sorted(new_rdb, key=lambda r: (r['file'], r['off']))
json.dump(m115, open(OUT + r"\번역_마스터_115.json", 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(untr, open(OUT + r"\_rdb_untr.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
bf = Counter(r['file'] for r in untr)
print("미번역 분포:", dict(bf))
print("\n미번역 전체:" if len(untr) <= 60 else "\n미번역 상위 60:")
for r in untr[:60]:
    print(f"  {r['file']:18s} 0x{r['off']:<7x} 예산{r['maxb']:4d}  {r['jp']!r}")
