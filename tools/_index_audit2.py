# -*- coding: utf-8 -*-
"""A/B의 변경 바이트가 어느 청크(타입/이름)에 속하는지 매핑 + 청크 타입 분포."""
import os, sys, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT)
def u32(b,o): return struct.unpack_from("<I",b,o)[0]

o=open("COMMON_2D-o.CHK",'rb').read()
a=open("COMMON_2D-한글폰트삽입.CHK",'rb').read()
bb=open("repack_in/COMMON_2D.CHK",'rb').read()
CHK=32
di=u32(o,CHK+16); ds=u32(o,CHK+20)

# 청크 열거 (타입 + 이름)
chunks=[]
pos=CHK+di; hi=CHK+ds
while pos<hi:
    ts=u32(o,pos+8); ct=o[pos+16:pos+24]
    if ts==0 or pos+ts>len(o): break
    nm=o[pos+32:pos+64].split(b"\x00",1)[0].decode("ascii","ignore")
    chunks.append((pos,ts,ct,nm))
    pos+=ts
print(f"청크 {len(chunks)}개, 청크영역 [0x{CHK+di:x}, 0x{hi:x})")

# 타입 분포
from collections import Counter
cnt=Counter(c[2] for c in chunks)
print("타입 분포:", {k.decode(errors='replace'):v for k,v in cnt.items()})

def diff_regions(x,y):
    rs=[]; i=0; N=min(len(x),len(y))
    while i<N:
        if x[i]!=y[i]:
            j=i
            while j<N and x[j]!=y[j]: j+=1
            rs.append((i,j)); i=j
        else: i+=1
    return rs

import bisect
starts=[c[0] for c in chunks]
def chunk_of(off):
    k=bisect.bisect_right(starts,off)-1
    if k<0: return None
    pos,ts,ct,nm=chunks[k]
    return (k,pos,ts,ct,nm) if off<pos+ts else None

for label,x in (("폰트A",a),("폰트B",bb)):
    rs=diff_regions(o,x)
    # 변경이 걸린 청크 집계
    hit=Counter(); hitbytes=Counter(); examples={}
    for s,e in rs:
        c=chunk_of(s)
        key=(c[4] or c[3].decode(errors='replace')) if c else f"영역외(0x{s:x})"
        hit[key]+=1; hitbytes[key]+=e-s
        if key not in examples and c: examples[key]=(c[1],c[2],c[3])
    print(f"\n===== {label}: 변경 {len(rs)}구간이 걸친 청크 {len(hit)}개 =====")
    for key,nb in sorted(hitbytes.items(), key=lambda kv:-kv[1])[:25]:
        ex=examples.get(key)
        extra=f" (청크@0x{ex[0]:x} ts={ex[1]} {ex[2].decode(errors='replace')})" if ex else ""
        print(f"  {key:28s} 변경 {nb:>9,}B / {hit[key]}구간{extra}")
