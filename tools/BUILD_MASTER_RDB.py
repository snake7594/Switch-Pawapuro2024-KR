# -*- coding: utf-8 -*-
"""RDB 번역 역추출: 배포본(repack_out) vs 원본(.) diff 세그 → _rdb_master_rows.json
각 세그: {file, off, jp(원본), ko(배포본 tsv역디코드), maxb}"""
import sys, os, json, time
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
TSV = load_tsv()
TSVR = {v: k for k, v in TSV.items()}
def dec_ko(s): return ''.join(TSVR.get(c, c) for c in s)

SKIP = {'COMMON_2D.CHK', 'COMMON_2D_ADD.CHK'}
DEP = rdblib.RDB('repack_out')
ORG = rdblib.RDB('.')
rows = []
t0 = time.time(); n = 0
for name, ent in DEP.idx.items():
    if ent['flag'] not in (0, 0x20) or name in SKIP or name not in ORG.idx: continue
    n += 1
    try:
        db = DEP.read_body(name); ob = ORG.read_body(name)
    except Exception:
        continue
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
        oe = ob.find(b'\x00', st)
        de = db.find(b'\x00', st)
        if oe < 0 or de < 0: continue
        try:
            jp = ob[st:oe].decode('utf-8')
            ko = dec_ko(db[st:de].decode('utf-8'))
        except UnicodeDecodeError:
            continue
        T = 0; k = oe
        while k < len(ob) and ob[k] == 0: T += 1; k += 1
        maxb = (oe - st) + (T - 1 if T > 0 else 0)
        rows.append({'file': name, 'off': st, 'jp': jp, 'ko': ko, 'maxb': maxb})
    if n % 3000 == 0: print(f'  {n} slots, rows {len(rows)} ({time.time()-t0:.0f}s)', flush=True)
DEP.close(); ORG.close()
json.dump(rows, open('_rdb_master_rows.json', 'w', encoding='utf-8'), ensure_ascii=False)
print(f"완료 {time.time()-t0:.0f}s: RDB 번역 세그 {len(rows):,}")
