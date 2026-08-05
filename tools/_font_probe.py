# -*- coding: utf-8 -*-
"""폰트 CHK의 RDI 아카이브명/슬롯/제자리 가능여부 확인."""
import os, sys, zlib, struct, bisect
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import REPACK_AUTO as R

dec, table, idx, rec_start = R.load_rdi("RES00.RDI")
print(f'RDI 항목 {len(table)}개')

# COMMON_2D 관련 항목 검색
print('\n=== RDI에서 COMMON_2D* 항목 ===')
for t in table:
    if 'COMMON_2D' in t['name']:
        loc = R.locate(t['stored'], t['flag'])
        print(f"  {t['name']:30s} flag={t['flag']:#x} DEC_SIZE={t['DEC_SIZE']} loc={loc}")

# 원본 레이아웃(gap 계산용)
laid = {"RES00.RDB": [], "RES10.RDB": []}
for t in table:
    loc = R.locate(t["stored"], t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
orig_size = {k: (os.path.getsize(k) if os.path.isfile(k) else 0) for k in laid}

def gap_to_next(rdb, local_byte):
    arr = laid[rdb]; j = bisect.bisect_right(arr, local_byte)
    nxt = arr[j] if j < len(arr) else orig_size[rdb]
    return nxt - local_byte

# 폰트 편집본 파일 후보
font_files = {
    'COMMON_2D.CHK': 'COMMON_2D-한글폰트삽입.CHK',
    'COMMON_2D_ADD.CHK': 'COMMON_2D_ADD-한글폰트삽입.CHK',
}
print('\n=== 폰트 제자리 가능 여부 검사 ===')
for arc, ff in font_files.items():
    if arc not in idx:
        # 이름에 .CHK 없이도 시도
        alt = arc.replace('.CHK','')
        arc2 = arc if arc in idx else (alt if alt in idx else None)
        if arc2 is None:
            print(f"  [{arc}] RDI에 없음 (대체명도 없음)"); continue
        arc = arc2
    if not os.path.isfile(ff):
        print(f"  [{arc}] 편집파일 {ff} 없음"); continue
    t = idx[arc]; loc = R.locate(t['stored'], t['flag'])
    rdb, off0, is10 = loc
    edited = open(ff,'rb').read()
    body = edited[32:]
    if t['flag'] > 0:
        comp = zlib.compress(body, 9)
        need_phys = R.align_up(32 + len(comp), R.SECTOR)
    else:
        need_phys = R.align_up(32 + len(body), R.SECTOR)
    gap = gap_to_next(rdb, off0)
    inplace = need_phys <= gap
    print(f"  [{arc}] {rdb} off=0x{off0:x} flag={t['flag']:#x}")
    print(f"     편집본문 {len(body)} → 압축 {len(comp) if t['flag']>0 else 'N/A'} 필요물리 {need_phys}")
    print(f"     다음까지 빈공간 {gap} → 제자리 가능? {'예 ✅' if inplace else '아니오(재배치 필요)'}")
