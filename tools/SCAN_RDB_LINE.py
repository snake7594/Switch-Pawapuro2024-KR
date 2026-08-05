# -*- coding: utf-8 -*-
"""RDB 텍스트 CHK 줄 규칙 위반 수집: 번역 폭 > 원문 폭 or 줄폭>24.
출력: _rdb_line_over.json [{file,off,jp,ko,jp_w,jp_lines,maxb}]"""
import sys, os, json, time, re
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib
import numpy as np

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSVR = {v: k for k, v in load_tsv().items()}
def dec(seg):
    try: return ''.join(TSVR.get(c, c) for c in seg.decode('utf-8'))
    except UnicodeDecodeError: return None
def is_full(c):
    o = ord(c)
    return (0x1100<=o<=0x11ff or 0xac00<=o<=0xd7a3 or 0x3000<=o<=0x30ff or 0x3400<=o<=0x9fff
            or 0xff00<=o<=0xff60 or 0xffe0<=o<=0xffe6 or 0x2e80<=o<=0x2fdf or 0xf900<=o<=0xfaff)
def width(s): return sum(1.0 if is_full(c) else 0.5 for c in s if c != '\n')
def maxlinew(s): return max((width(ln) for ln in s.split('\n')), default=0)
def has_kana(s): return any('぀' <= c <= 'ヿ' for c in s)

DEP = rdblib.RDB('repack_out'); ORG = rdblib.RDB('.')
SKIP = {'COMMON_2D.CHK', 'COMMON_2D_ADD.CHK'}
rows = []; n = 0; t0 = time.time()
for name, ent in DEP.idx.items():
    if ent['flag'] not in (0, 0x20) or name in SKIP or name not in ORG.idx: continue
    n += 1
    try:
        db = DEP.read_body(name); ob = ORG.read_body(name)
    except Exception: continue
    if db is None or ob is None or db == ob or len(db) != len(ob): continue
    a = np.frombuffer(bytes(db), dtype=np.uint8); b = np.frombuffer(ob, dtype=np.uint8)
    diff = np.nonzero(a != b)[0]
    if len(diff) == 0: continue
    starts = set()
    for x in diff.tolist():
        st = x
        while st > 0 and ob[st-1] != 0: st -= 1
        starts.add(st)
    for st in starts:
        if ob[st] == 0: continue
        oe = ob.find(b'\x00', st); de = db.find(b'\x00', st)
        if oe < 0 or de < 0: continue
        try: jp = ob[st:oe].decode('utf-8')
        except UnicodeDecodeError: continue
        ko = dec(db[st:de])
        if ko is None: continue
        # 대사/도움말성(가나 포함) + 위반
        if not has_kana(jp): continue
        jw = width(jp); kw = width(ko)
        if kw > jw + 0.5 or ('\n' in ko and maxlinew(ko) > 24.0):
            T = 0; k = de
            while k < len(db) and db[k] == 0: T += 1; k += 1
            rows.append({'file': name, 'off': st, 'jp': jp, 'ko': ko, 'jp_w': round(jw, 1),
                         'jp_lines': jp.count('\n')+1, 'maxb': (oe-st)+(T-1 if T > 0 else 0)})
    if n % 3000 == 0: print(f'  {n} slots, over {len(rows)} ({time.time()-t0:.0f}s)', flush=True)
DEP.close(); ORG.close()
json.dump(rows, open('_rdb_line_over.json', 'w', encoding='utf-8'), ensure_ascii=False)
print(f"완료 {time.time()-t0:.0f}s: RDB 줄규칙 위반 {len(rows)}")
