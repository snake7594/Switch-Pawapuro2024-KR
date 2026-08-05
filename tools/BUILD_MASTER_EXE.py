# -*- coding: utf-8 -*-
"""단일 마스터 생성: 현재 배포본(main-safe28)에 실제 주입된 모든 exe 번역을 offset 기준 역추출.
- 원본 main vs 배포본 diff → strings 영역(>DYN_END)의 번역된 세그
- 각 세그: {off, jp(원본), ko(배포본 tsv역디코드), maxb}
- 죽은풀(원본 시작바이트=0=redirect 타깃)·동적영역 제외
결과: exe_마스터.json  (이 파일 하나가 exe 번역의 유일한 진실)"""
import sys, os, json
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
TSVR = {v: k for k, v in TSV.items()}
def dec_ko(s): return ''.join(TSVR.get(c, c) for c in s)

ob = open('main', 'rb').read()
dep = open('inject_out/main-safe28', 'rb').read()
assert len(ob) == len(dep)
DYN_END = 0x3d2551d
a = np.frombuffer(dep, dtype=np.uint8); b = np.frombuffer(ob, dtype=np.uint8)
diff = np.nonzero(a != b)[0]
sel = diff[diff >= DYN_END]
print(f"strings 영역 diff {len(sel):,}")

# 세그먼트 시작(원본 NUL 경계) 추출
starts = set()
for x in sel.tolist():
    st = x
    while st > DYN_END and ob[st-1] != 0: st -= 1
    starts.add(st)
print(f"번역된 세그먼트 {len(starts):,}")

rows = []
skip_pool = skip_dec = 0
for st in sorted(starts):
    if ob[st] == 0:        # 죽은풀 redirect 타깃
        skip_pool += 1; continue
    oe = ob.find(b'\x00', st)
    de = dep.find(b'\x00', st)
    if oe < 0 or de < 0: continue
    try:
        jp = ob[st:oe].decode('utf-8')
        ko = dec_ko(dep[st:de].decode('utf-8'))
    except UnicodeDecodeError:
        skip_dec += 1; continue
    # maxb: 원본 세그 + 후행 NUL 런
    T = 0; k = oe
    while k < len(ob) and ob[k] == 0: T += 1; k += 1
    maxb = (oe - st) + (T - 1 if T > 0 else 0)
    rows.append({'off': st, 'jp': jp, 'ko': ko, 'maxb': maxb})
print(f"마스터 항목 {len(rows):,} (풀제외 {skip_pool}, 디코드실패 {skip_dec})")

master = {
    'meta': {
        'source': 'main-safe28 역추출',
        'note': 'exe(실행파일) 번역 단일 마스터. off=파일오프셋, maxb=바이트예산(한글3B/ASCII1B). ko만 수정 후 APPLY_MASTER_EXE.py로 재주입.',
        'count': len(rows),
    },
    'rows': rows,
}
json.dump(master, open('exe_마스터.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print("→ exe_마스터.json")
# 표본
for r in rows[:5]: print('  ', r['off'], repr(r['jp'][:24]), '→', repr(r['ko'][:24]))
