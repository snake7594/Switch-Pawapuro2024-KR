# -*- coding: utf-8 -*-
"""번역_마스터.json 을 사람이 읽을 수 있는 '레코드 한 줄' 형식으로 정리.

한 줄짜리로 뭉쳐진 파일을 열어볼 수 있게 만들고, 편집 후에도 형식을 되돌린다.
내용은 절대 바꾸지 않는다(정리 전후 데이터 동일성을 검증한 뒤에만 저장).

사용:  python tools/FORMAT_MASTER.py [파일경로]
"""
import sys, os, json, shutil
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from master_io import load_master, save_master

_R = os.environ.get("PAWA_ROOT")
if _R and len(sys.argv) < 2: os.chdir(_R)
path = sys.argv[1] if len(sys.argv) > 1 else '번역_마스터.json'
if not os.path.exists(path): sys.exit(f"없음: {path}")

before = os.path.getsize(path)
m = load_master(path)
tmp = path + '.tmp'
save_master(m, tmp)

# 안전장치: 정리본이 원본과 '데이터로서' 같은지 확인한 뒤에만 교체
if load_master(tmp) != m:
    os.remove(tmp); sys.exit("✗ 정리 결과가 원본과 다릅니다 — 중단(원본 유지)")
shutil.move(tmp, path)
after = os.path.getsize(path)
lines = sum(1 for _ in open(path, encoding='utf-8'))
print(f"정리 완료: {path}")
print(f"  {before/1048576:.1f}MB → {after/1048576:.1f}MB, {lines:,}줄")
for k in ('exe', 'exe_ext', 'rdb'):
    if k in m: print(f"  {k:8s} {len(m[k]):,}개")
print("  각 항목이 한 줄이므로 편집기에서 원하는 문구를 검색해 그 줄의 \"ko\" 만 고치면 됩니다.")
