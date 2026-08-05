# -*- coding: utf-8 -*-
"""이미지(NX SUR) 포함 스캔 CHK를 repack_out에서 원본으로 되돌림(제자리 재주입).
   스캔 방식이 텍스처 데이터를 문자열로 오인해 덮어써 이미지 손상 → 원복.
   (이미지 CHK의 텍스트는 일본어로 되돌아가지만 이미지 정상화)."""
import os, sys, zlib, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
RES="RES_추출원본"; OUT="repack_out"

decp, tabp, idxp, rsp = R.load_rdi(os.path.join(OUT,"RES00.RDI"))

# 대상: 이미지 포함 + 스캔 패치(크기불변, 변경있음)
files=[fn for fn in os.listdir("repack_in") if fn.endswith(".CHK") and fn not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")]
targets=[]
for fn in files:
    o=os.path.join(RES,fn); k=os.path.join("repack_in",fn)
    if not os.path.isfile(o): continue
    if os.path.getsize(o)!=os.path.getsize(k): continue  # STRING 제외
    ob=open(o,'rb').read()
    if ob==open(k,'rb').read(): continue                 # 무변경 제외
    if ob.find(b'NX  SUR ')<0: continue                  # 이미지 없으면 제외
    if fn in idxp: targets.append(fn)
print(f"되돌릴 이미지-스캔 CHK: {len(targets)}개")

fh={}
try:
    reverted=0
    for fn in targets:
        t=idxp[fn]; loc=R.locate(t["stored"],t["flag"])
        if loc is None: continue
        rdb, off, is10 = loc
        if rdb not in fh: fh[rdb]=open(os.path.join(OUT,rdb),"r+b")
        key=R.file_key(fn)
        # 원본 슬롯 헤더(권위) — repack_out의 현재 슬롯에서 읽음(이름/구조 동일)
        fh[rdb].seek(off); hraw=fh[rdb].read(32)
        header=bytearray(R.crypt(hraw,key))
        body=open(os.path.join(RES,fn),"rb").read()[32:]   # 원본 본문
        if t["flag"]>0:
            comp=zlib.compress(body,9); new_decsize=R.align_up(len(body),4)
            struct.pack_into("<I",header,0x18,len(comp))
        else:
            comp=body; new_decsize=R.align_up(32+len(body),4)
            struct.pack_into("<I",header,0x18,new_decsize)
        struct.pack_into("<I",header,0x1C,off//R.SECTOR)
        need=R.align_up(32+len(comp),R.SECTOR)
        blob=bytearray(need); blob[:32]=header; blob[32:32+len(comp)]=comp
        enc=R.crypt(bytes(blob),key)
        fh[rdb].seek(off); fh[rdb].write(enc)
        rp=rsp+t["i"]*9
        struct.pack_into("<I",decp,rp,t["stored"])          # offset 불변
        struct.pack_into("<I",decp,rp+4,new_decsize)
        reverted+=1
finally:
    for f in fh.values(): f.close()
R.save_rdi(decp, os.path.join(OUT,"RES00.RDI"))
print(f"되돌림 완료: {reverted}개. repack_out RDI 저장.")
print("스톡 main과 함께 테스트.")
