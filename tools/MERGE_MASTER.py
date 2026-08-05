# -*- coding: utf-8 -*-
"""통합 마스터 생성: exe + RDB → 번역_마스터.json (단일 파일)
구조: {meta, exe:[{off,jp,ko,maxb}], rdb:[{file,off,jp,ko,maxb}]}"""
import sys, os, json
import sys as _s, os as _o
_s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
from master_io import save_master   # 가독(레코드 한 줄) 형식 유지
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용

exe = json.load(open('exe_마스터.json', encoding='utf-8'))['rows']
rdb = json.load(open('_rdb_master_rows.json', encoding='utf-8'))
master = {
    'meta': {
        'note': '실황2024 한글 번역 통합 마스터. ko만 수정 후 APPLY_MASTER.py --deploy 실행.',
        'exe_source': 'main-safe28 (실행파일: 대사·메뉴·이름·설명)',
        'rdb_source': 'repack_out (RES00/RES10 CHK: 선수명·소개문·UI라벨 등)',
        'field': 'off=오프셋(수정금지), file=RDB파일명, jp=원문, ko=번역(수정대상), maxb=바이트예산(한글3B/ASCII1B)',
        'exe_count': len(exe), 'rdb_count': len(rdb),
    },
    'exe': exe,
    'rdb': rdb,
}
save_master(master)
print(f"통합 마스터: exe {len(exe):,} + rdb {len(rdb):,} = {len(exe)+len(rdb):,} 항목 → 번역_마스터.json")
print(f"파일 크기: {os.path.getsize('번역_마스터.json')/1e6:.1f} MB")
