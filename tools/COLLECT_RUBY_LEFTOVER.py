# -*- coding: utf-8 -*-
"""배포본(exe main-safe28 + RDB repack_out)에서 루비/가나 잔존 슬롯 전수 수집.
원문(orig)의 '단어／かな' 형식 슬롯 중 배포본 ko에 가나/／가 남은 것 → 재번역 입력.
출력: _ruby_fix_in/*.json  ([{key, jp, ko_now, maxb, ruby_word}])"""
import sys, os, json, re
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np
import rdblib

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()
TSVR = {v: k for k, v in TSV.items()}
def dec(bs):
    try: return ''.join(TSVR.get(c, c) for c in bs.decode('utf-8'))
    except UnicodeDecodeError: return None
KANA = re.compile(r'[぀-ゟ゠-ヿ]')
ALLOW = set('ー・～')
RUBY_JP = re.compile(r'^(.+?)／([぀-ゟ゠-ヿー]+)$')
def has_left(ko):
    if ko is None: return False
    if '／' in ko: return True
    return any(KANA.match(c) and c not in ALLOW for c in ko)

rows = []
# ---- exe ----
orig = open('main', 'rb').read(); dep = open('inject_out/main-safe28', 'rb').read()
DYN = 0x3d2551d
a = np.frombuffer(dep, dtype=np.uint8); b = np.frombuffer(orig, dtype=np.uint8)
diff = np.nonzero(a != b)[0]; sel = diff[diff >= DYN]
starts = set()
for x in sel.tolist():
    st = x
    while st > DYN and orig[st-1] != 0: st -= 1
    starts.add(st)
for st in starts:
    if orig[st] == 0: continue
    oe = orig.find(b'\x00', st); de = dep.find(b'\x00', st)
    try: jp = orig[st:oe].decode('utf-8')
    except UnicodeDecodeError: continue
    ko = dec(dep[st:de])
    if not has_left(ko): continue
    T = 0; k = oe
    while k < len(orig) and orig[k] == 0: T += 1; k += 1
    maxb = (oe - st) + (T - 1 if T > 0 else 0)
    m = RUBY_JP.match(jp)
    rows.append({'src': 'exe', 'off': st, 'jp': jp, 'ko_now': ko, 'maxb': maxb,
                 'ruby_word': m.group(1) if m else None})
print(f"exe 잔존 {len([r for r in rows if r['src']=='exe'])}")

# ---- rdb ----
DEP = rdblib.RDB('repack_out'); ORG = rdblib.RDB('.')
import time; t0 = time.time(); n = 0
for name, ent in DEP.idx.items():
    if ent['flag'] not in (0, 0x20) or name not in ORG.idx: continue
    n += 1
    try: db = DEP.read_body(name); ob = ORG.read_body(name)
    except Exception: continue
    if db is None or ob is None or db == ob or len(db) != len(ob): continue
    aa = np.frombuffer(bytes(db), dtype=np.uint8); bb = np.frombuffer(ob, dtype=np.uint8)
    dd = np.nonzero(aa != bb)[0]
    if len(dd) == 0: continue
    ss = set()
    for x in dd.tolist():
        st = x
        while st > 0 and ob[st-1] != 0: st -= 1
        ss.add(st)
    for st in ss:
        if ob[st] == 0: continue
        oe = ob.find(b'\x00', st); de = db.find(b'\x00', st)
        try: jp = ob[st:oe].decode('utf-8')
        except UnicodeDecodeError: continue
        ko = dec(db[st:de])
        if not has_left(ko): continue
        m = RUBY_JP.match(jp)
        # 진짜 루비/대사만: 앞이 단어이거나 가나 포함 문장
        T = 0; k = oe
        while k < len(ob) and ob[k] == 0: T += 1; k += 1
        maxb = (oe - st) + (T - 1 if T > 0 else 0)
        rows.append({'src': 'rdb', 'file': name, 'off': st, 'jp': jp, 'ko_now': ko,
                     'maxb': maxb, 'ruby_word': m.group(1) if m else None})
    if n % 3000 == 0: print(f'  rdb {n} ({time.time()-t0:.0f}s) rows {len(rows)}', flush=True)
DEP.close(); ORG.close()
print(f"rdb 잔존 {len([r for r in rows if r['src']=='rdb'])}, 총 {len(rows)}")
json.dump(rows, open('_ruby_leftover.json', 'w', encoding='utf-8'), ensure_ascii=False)
# 배치 분할
os.makedirs('_ruby_fix_in', exist_ok=True); os.makedirs('_ruby_fix_out', exist_ok=True)
B = 120; bn = 0
for s in range(0, len(rows), B):
    batch = [{'k': i+s, 'jp': r['jp'], 'ko_now': r['ko_now'], 'maxb': r['maxb']} for i, r in enumerate(rows[s:s+B])]
    json.dump(batch, open(f'_ruby_fix_in/r{bn:03d}.json', 'w', encoding='utf-8'), ensure_ascii=False)
    bn += 1
print(f"배치 {bn}")
