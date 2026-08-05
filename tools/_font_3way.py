# -*- coding: utf-8 -*-
"""원본 vs 폰트A(정상) vs 폰트B(깨진빌드) COMMON_2D 비교.
   각 폰트가 원본에서 어느 영역을 바꿨는지 → 폰트B가 이미지영역을 손상시켰는지."""
import os, sys, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT)

orig_cand=["COMMON_2D-o.CHK","RES_추출원본/COMMON_2D.CHK"]
ORIG=None
for c in orig_cand:
    if os.path.isfile(c): ORIG=c; break
A="COMMON_2D-한글폰트삽입.CHK"      # 정상(테스트됨)
B="repack_in/COMMON_2D.CHK"        # 깨진빌드
print(f"원본: {ORIG}\n폰트A(정상): {A}\n폰트B(깨짐): {B}")

o=open(ORIG,'rb').read(); a=open(A,'rb').read(); b=open(B,'rb').read()
print(f"크기: 원본{len(o)} A{len(a)} B{len(b)}")

def diff_regions(x,y,minlen=1):
    """x,y 다른 구간 목록 [(start,end)]"""
    regions=[]; i=0; N=min(len(x),len(y))
    while i<N:
        if x[i]!=y[i]:
            j=i
            while j<N and x[j]!=y[j]: j+=1
            regions.append((i,j))
            i=j
        else: i+=1
    if len(x)!=len(y):
        regions.append((N, max(len(x),len(y))))
    return regions

ra=diff_regions(o,a)
rb=diff_regions(o,b)
def span(rs):
    return sum(e-s for s,e in rs)
print(f"\n폰트A가 원본에서 바꾼 영역: {len(ra)}구간, 총 {span(ra)} bytes")
print(f"  범위: 0x{ra[0][0]:x} ~ 0x{ra[-1][1]:x}" if ra else "  없음")
print(f"폰트B가 원본에서 바꾼 영역: {len(rb)}구간, 총 {span(rb)} bytes")
print(f"  범위: 0x{rb[0][0]:x} ~ 0x{rb[-1][1]:x}" if rb else "  없음")

# NX SUR 이미지 청크 위치
def surs(x):
    r=[]; p=0
    while True:
        i=x.find(b'NX  SUR ',p)
        if i<0: break
        r.append(i); p=i+1
    return r
print(f"\n원본 NX SUR 청크 {len(surs(o))}개")

# 폰트B만 바꾼 영역(A는 안 바꿨는데 B는 바꾼 = B의 추가 손상 의심)
aset=set()
for s,e in ra: aset.update(range(s,min(e,len(o))))
b_only=[]
for s,e in rb:
    # 이 구간에서 A는 안 건드린 부분
    only_s=None
    for x in range(s,min(e,len(o))):
        if x not in aset:
            if only_s is None: only_s=x
        else:
            if only_s is not None: b_only.append((only_s,x)); only_s=None
    if only_s is not None: b_only.append((only_s,min(e,len(o))))
print(f"\n★ 폰트B만 바꾼 영역(A는 안 건드림) = B의 추가 변경: {len(b_only)}구간, 총 {span(b_only)} bytes")
for s,e in b_only[:15]:
    print(f"   0x{s:x}~0x{e:x} (len {e-s})  orig={o[s:min(e,s+8)].hex()} B={b[s:min(e,s+8)].hex()}")
