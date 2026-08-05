# -*- coding: utf-8 -*-
"""CHK 청크 구조 덤프 + 원본/재구성 비교: STRING 성장으로 이미지 청크가 밀렸는지,
   청크 디렉토리(sizes[]/오프셋)가 갱신됐는지 진단."""
import os, sys, struct, re
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT)

def dump(path, label):
    b=open(path,'rb').read()
    print(f"\n===== {label}: {path}  (파일크기 {len(b)}) =====")
    # 슬롯헤더 32B 여부: 'CHK ' 매직 위치 확인
    chk_at = b.find(b'CHK ')
    print(f"  'CHK ' 매직 @0x{chk_at:x}")
    base = chk_at  # CHK content 시작
    # CHK+0x2C 총크기
    if base+0x30<=len(b):
        total=struct.unpack_from('<I',b,base+0x2C)[0]
        print(f"  CHK총크기@+0x2C = {total} (0x{total:x})")
    # 청크 디렉토리 헤더 (CHK+0x20 기준)
    dh=base+0x20
    if dh+0x20<=len(b):
        di_off=struct.unpack_from('<I',b,dh+16)[0]
        ds_off=struct.unpack_from('<I',b,dh+20)[0]
        dcount=struct.unpack_from('<I',b,dh+24)[0]
        print(f"  청크디렉토리@+0x20: data_info_off={di_off} data_start_off={ds_off} data_count={dcount}")
        # sizes[] @ dh+28
        sizes=[struct.unpack_from('<I',b,dh+28+4*i)[0] for i in range(min(dcount,40))]
        print(f"  sizes[] (앞 {len(sizes)}개): {sizes}")
    # 모든 4바이트정렬 ASCII 매직 청크 스캔
    print("  --- 청크 매직 스캔 (magic @off, size@+8) ---")
    for m in [b'HEADER', b'STRING', b'TABLE', b'CHUNKEND', b'NX  SUR ']:
        pos=0
        while True:
            i=b.find(m,pos)
            if i<0: break
            sz=struct.unpack_from('<I',b,i+8)[0] if i+12<=len(b) else -1
            print(f"    {m.decode(errors='replace'):10s} @0x{i:x}  size@+8={sz}")
            pos=i+1
            if pos>len(b): break

for src, lab in [("RES_추출원본/APPSELECT.CHK","원본"), ("repack_in/APPSELECT.CHK","재구성(패치)")]:
    if os.path.isfile(src): dump(src, lab)
    else: print(f"\n{src} 없음")
