# -*- coding: utf-8 -*-
"""배포 전 구조 검증: 전 슬롯 헤더/압축 무결성 표본 + 핵심 파일 재독."""
import sys, os, random, time
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib

D = rdblib.RDB('repack_out')
names = [n for n, e in D.idx.items() if e['flag'] in (0, 0x20)]
print(f"슬롯 {len(D.table)}, 읽기대상 {len(names)}")
random.seed(42)
sample = random.sample(names, 3000)
# 감사에서 손댄 파일은 전부 포함
import json
rep = json.load(open('_bogus_report.json', encoding='utf-8'))
check = list(dict.fromkeys(list(rep.keys()) + sample +
    ['NAME_DIC.CHK', 'SEN_MAIN.CHK', 'SEN_MAIN_2ND.CHK', 'SEN_TEXT.CHK', 'SEN_TEXT_2ND.CHK',
     'HSIM_DT_TEAM.CHK', 'COMMON_2D.CHK', 'COMMON_2D_ADD.CHK']))
bad = []
t0 = time.time()
for i, n in enumerate(check):
    if n not in D.idx: continue
    try:
        b = D.read_body(n)
        if b is None: bad.append((n, 'None'))
    except Exception as e:
        bad.append((n, str(e)[:60]))
    if (i+1) % 1000 == 0: print(f"  {i+1}/{len(check)} ({time.time()-t0:.0f}s)", flush=True)
D.close()
print(f"검사 {len(check)}건, 실패 {len(bad)}")
for n, e in bad[:20]: print(f"  FAIL {n}: {e}")
