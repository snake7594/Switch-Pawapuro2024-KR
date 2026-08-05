# -*- coding: utf-8 -*-
"""COMMON_2D 원본/폰트A/폰트B 인덱스 정합성 감사.
   CHK 구조: CHK=32(슬롯헤더 뒤). di_off@CHK+16, ds_off@CHK+20, dc@CHK+24, sizes[]@CHK+28.
   블롭 위치 = CHK+ds_off + prefix_sum(sizes). NX SUR: name@+32, blobsize@+0x70.
   검사: 길이가 변한 블롭 → sizes[]·+0x70·데이터이동·총크기 모두 갱신됐는지."""
import os, sys, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT)
def u32(b,o): return struct.unpack_from("<I",b,o)[0]

def parse(path):
    b=open(path,'rb').read()
    CHK=32
    di=u32(b,CHK+16); ds=u32(b,CHK+20); dc=u32(b,CHK+24)
    sizes=[u32(b,CHK+28+4*i) for i in range(dc)]
    pref=[0]
    for s in sizes: pref.append(pref[-1]+s)
    data_base=CHK+ds
    # 청크 열거
    pos=CHK+di; hi=CHK+ds; texs=[]; chunks=[]
    while pos<min(hi,len(b)):
        if pos+0xE0>len(b): break
        ts=u32(b,pos+8); ct=b[pos+16:pos+24]
        if ts==0 or pos+ts>len(b): break
        chunks.append((pos,ts,ct))
        if ct==b"NX  SUR ":
            nm=b[pos+32:pos+64].split(b"\x00",1)[0].decode("ascii","ignore")
            texs.append(dict(name=nm,w=u32(b,pos+64),h=u32(b,pos+68),
                             fmt=u32(b,pos+0x54),sz=u32(b,pos+0x70),hdr_pos=pos))
        pos+=ts
    # two-pointer 블롭 매핑
    bp=0
    for t in texs:
        while bp<len(sizes) and sizes[bp]!=t["sz"]: bp+=1
        if bp<len(sizes):
            t["size_idx"]=bp; t["blob_off"]=data_base+pref[bp]; bp+=1
        else:
            t["size_idx"]=None; t["blob_off"]=None
    return dict(b=b,di=di,ds=ds,dc=dc,sizes=sizes,pref=pref,data_base=data_base,
                texs=texs,chunks=chunks,fsize=len(b))

O=parse("COMMON_2D-o.CHK")
A=parse("COMMON_2D-한글폰트삽입.CHK")
B=parse("repack_in/COMMON_2D.CHK")

print("=== 헤더 필드 비교 ===")
print(f"{'':12s} {'원본':>12s} {'폰트A':>12s} {'폰트B':>12s}")
for k in ("fsize","di","ds","dc"):
    print(f"  {k:10s} {O[k]:>12} {A[k]:>12} {B[k]:>12}")
print(f"  texs       {len(O['texs']):>12} {len(A['texs']):>12} {len(B['texs']):>12}")
print(f"  chunks     {len(O['chunks']):>12} {len(A['chunks']):>12} {len(B['chunks']):>12}")

print("\n=== sizes[] 배열 차이 ===")
diff_sa=[i for i in range(min(O['dc'],A['dc'])) if O['sizes'][i]!=A['sizes'][i]]
diff_sb=[i for i in range(min(O['dc'],B['dc'])) if O['sizes'][i]!=B['sizes'][i]]
print(f"  원본↔A 다른 엔트리: {len(diff_sa)}개 {[ (i,O['sizes'][i],A['sizes'][i]) for i in diff_sa[:10]]}")
print(f"  원본↔B 다른 엔트리: {len(diff_sb)}개 {[ (i,O['sizes'][i],B['sizes'][i]) for i in diff_sb[:10]]}")

print("\n=== NX SUR 헤더(+0x70 블롭크기) 차이 ===")
def tex_by_name(P): return {t["name"]:t for t in P["texs"]}
to,ta,tb=tex_by_name(O),tex_by_name(A),tex_by_name(B)
for label,tx in (("A",ta),("B",tb)):
    diffs=[(n,to[n]["sz"],tx[n]["sz"]) for n in to if n in tx and to[n]["sz"]!=tx[n]["sz"]]
    print(f"  원본↔{label} sz 다른 텍스처: {len(diffs)}개")
    for n,so,sn in diffs[:10]: print(f"     {n}: {so} -> {sn} (Δ{sn-so:+d})")

print("\n=== 블롭 데이터 실제 차이 (원본 기준 오프셋으로 비교) ===")
# 각 텍스처 블롭이 원본과 A/B에서 (자기 위치 기준) 동일한지
def blob(P,t):
    if t["blob_off"] is None: return b""
    return P["b"][t["blob_off"]:t["blob_off"]+t["sz"]]
cha=[]; chb=[]
for n in to:
    if n in ta and blob(O,to[n])!=blob(A,ta[n]): cha.append(n)
    if n in tb and blob(O,to[n])!=blob(B,tb[n]): chb.append(n)
print(f"  A에서 내용 바뀐 텍스처: {len(cha)}개: {cha[:15]}")
print(f"  B에서 내용 바뀐 텍스처: {len(chb)}개: {chb[:15]}")

print("\n=== two-pointer 매핑 실패 여부 ===")
for label,P in (("원본",O),("A",A),("B",B)):
    fail=[t["name"] for t in P["texs"] if t["blob_off"] is None]
    print(f"  {label}: 매핑실패 {len(fail)}개 {fail[:8]}")

print("\n=== 데이터영역 총합 vs 파일크기 ===")
for label,P in (("원본",O),("A",A),("B",B)):
    total=P["data_base"]+P["pref"][-1]
    print(f"  {label}: data_base+sum(sizes)={total}  파일크기={P['fsize']}  (여유 {P['fsize']-total})")
