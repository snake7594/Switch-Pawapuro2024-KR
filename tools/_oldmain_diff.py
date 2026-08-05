# -*- coding: utf-8 -*-
"""예전 패치 main들 vs main-원본 세그먼트별 변경 분석 (크래시 원인 규명)."""
import sys, struct, hashlib
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
import os
os.chdir('!exefs-작업')

def segs(b):
    tx=struct.unpack_from('<III',b,0x10); ro=struct.unpack_from('<III',b,0x20); da=struct.unpack_from('<III',b,0x30)
    return dict(text=tx, ro=ro, data=da)

bo=open("main-원본","rb").read()
S=segs(bo)
print("main-원본 세그먼트: text fo=0x%x sz=0x%x | ro fo=0x%x sz=0x%x | data fo=0x%x sz=0x%x"%(
    S['text'][0],S['text'][2],S['ro'][0],S['ro'][2],S['data'][0],S['data'][2]))

for name in ("main","main-MOD0"):
    b=open(name,"rb").read()
    print(f"\n===== {name} (크기 {len(b)}, 원본대비 {len(b)-len(bo):+d}) =====")
    if len(b)!=len(bo):
        print("  ⚠️ 크기 다름 → NSO 재빌드(구조 변경). 세그먼트 헤더 비교:")
        s2=segs(b)
        for k in ('text','ro','data'):
            print(f"    {k}: 원본 fo=0x{S[k][0]:x} sz=0x{S[k][2]:x}  →  {name} fo=0x{s2[k][0]:x} sz=0x{s2[k][2]:x}")
        continue
    ao=np.frombuffer(bo,dtype=np.uint8); an=np.frombuffer(b,dtype=np.uint8)
    diff=np.nonzero(ao!=an)[0]
    print(f"  변경 바이트: {len(diff):,}")
    if len(diff)==0: continue
    for k in ('text','ro','data'):
        fo,mo,sz=S[k]
        cnt=((diff>=fo)&(diff<fo+sz)).sum()
        print(f"    {k:5s} [0x{fo:x},0x{fo+sz:x}): {cnt:,}바이트 변경")
    hdr=(diff<0x100).sum(); print(f"    헤더(0x0~0x100): {hdr}바이트")
    # .text 변경이 있으면 심각 (코드 손상)
    fo,mo,sz=S['text']
    tdiff=diff[(diff>=fo)&(diff<fo+sz)]
    if len(tdiff): print(f"    ⚠️ .text 코드 변경! 첫 위치 0x{tdiff[0]:x}")
