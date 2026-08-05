# -*- coding: utf-8 -*-
"""배포 RDB 전 슬롯: 잔여 미번역 일본어(가나 포함) 전수 수집.
- 대상: NUL경계 UTF-8 문자열, 히라가나/가타카나 포함(ー・～ 단독 제외), 제어문자 없음, 4B~400B
- tsv 디코드 후에도 가나가 남으면 미번역 JP로 판정(주입된 한국어는 한글로 디코드됨)
- 출력: _untr_rdb.json {jp: {occ:[[file,off,budget]], n}}"""
import sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV_R = {v: k for k, v in load_tsv().items()}
ALLOW_KANA = set('ー・～ヽヾゝゞ')
def kana_real(s):
    dec = ''.join(TSV_R.get(c, c) for c in s)
    return any((('぀' <= c <= 'ゟ') or ('゠' <= c <= 'ヿ')) and c not in ALLOW_KANA for c in dec)

D = rdblib.RDB('repack_out')
SKIP = {'COMMON_2D.CHK', 'COMMON_2D_ADD.CHK'}
out = {}
t0 = time.time(); n = 0
for name, ent in D.idx.items():
    if ent['flag'] not in (0, 0x20) or name in SKIP: continue
    n += 1
    try: b = D.read_body(name)
    except Exception: continue
    if b is None: continue
    pos = 0
    while pos < len(b):
        e = b.find(b'\x00', pos)
        if e < 0: break
        if 4 <= e - pos <= 400:
            seg = b[pos:e]
            try: s = seg.decode('utf-8')
            except UnicodeDecodeError: s = None
            if s and not any(ord(c) < 0x20 for c in s) and kana_real(s):
                T = 0; k = e
                while k < len(b) and b[k] == 0: T += 1; k += 1
                budget = (e - pos) + (T - 1 if T > 0 else 0)
                u = out.setdefault(s, {'occ': [], 'n': 0})
                if len(u['occ']) < 60: u['occ'].append([name, pos, budget])
                u['n'] += 1
        pos = e + 1
    if n % 3000 == 0: print(f'  {n} slots, 고유 {len(out)} ({time.time()-t0:.0f}s)', flush=True)
D.close()
json.dump(out, open('_untr_rdb.json', 'w', encoding='utf-8'), ensure_ascii=False)
print(f"완료 {time.time()-t0:.0f}s: 슬롯 {n}, 미번역 고유 {len(out)}, 총 {sum(v['n'] for v in out.values())} occ")
