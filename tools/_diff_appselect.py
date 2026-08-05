# -*- coding: utf-8 -*-
"""APPSELECT 원본 vs 패치(repack_in) 바이트 diff — 변경 위치가 텍스트인지 이미지/구조인지."""
import os, sys, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT)
fn="APPSELECT.CHK"
o=open(os.path.join("RES_추출원본",fn),'rb').read()
k=open(os.path.join("repack_in",fn),'rb').read()
print(f"원본 {len(o)}  패치 {len(k)}  동일크기={len(o)==len(k)}")

# NX SUR / STRING / 데이터영역 위치
sur=[]
p=0
while True:
    i=o.find(b'NX  SUR ',p)
    if i<0: break
    sur.append(i); p=i+1
print(f"NX SUR 청크 위치: {[hex(x) for x in sur]}")
str_pos=o.find(b'STRING')
print(f"STRING @ {hex(str_pos) if str_pos>=0 else '없음'}")

# 청크 디렉토리 헤더
chk=o.find(b'CHK ')
dh=chk+0x20
di_off=struct.unpack_from('<I',o,dh+16)[0]
ds_off=struct.unpack_from('<I',o,dh+20)[0]
dcount=struct.unpack_from('<I',o,dh+24)[0]
print(f"청크디렉토리: di_off={di_off}(0x{di_off:x}) ds_off={ds_off}(0x{ds_off:x}) count={dcount}")

# 변경 구간 찾기
diffs=[]
i=0; N=min(len(o),len(k))
while i<N:
    if o[i]!=k[i]:
        j=i
        while j<N and o[j]!=k[j]: j+=1
        diffs.append((i,j))
        i=j
    else: i+=1
print(f"\n변경 구간 {len(diffs)}개:")
for a,b2 in diffs[:40]:
    # 이 구간이 어디에 속하는지 판단
    where="?"
    if str_pos>=0 and a>=str_pos: where="STRING이후"
    region = "이미지영역가능" if (a < (sur[-1]+0x100000 if sur else 0) and (not sur or a>sur[0])) else ""
    ctx_o=o[max(0,a-4):a+min(12,b2-a+4)]
    ctx_k=k[max(0,a-4):a+min(12,b2-a+4)]
    print(f"  0x{a:x}~0x{b2:x} (len {b2-a})  orig={ctx_o.hex()} new={ctx_k.hex()}")

# 변경이 데이터(이미지) 영역에 있는지: ds_off 이후인지
print(f"\n(data_start_off={ds_off}. 변경 오프셋이 이보다 크면 이미지/데이터 영역 손상 의심)")
