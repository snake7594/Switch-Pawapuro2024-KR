# -*- coding: utf-8 -*-
"""재배치 가설 검증 빌드:
   - 폰트A를 repack_out의 '원본 슬롯'에 제자리 패치(재배치 제거, 한글폰트 유지)
   - 나머지 재배치된 텍스트 CHK는 RDI를 원본으로 되돌림(원본 슬롯의 일본어 그대로 읽음)
   결과: 재배치 0, RDB 원본 레이아웃, 한글폰트+스캔한글텍스트 유지(STRING CHK만 일본어).
   → 게임이 정상 실행되면 '재배치'가 멈춤/이미지깨짐의 원인.
   출력: repack_out 제자리 수정 (RES00.RDB/RES10.RDB/RES00.RDI)."""
import os, sys, zlib, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R

OUT="repack_out"
deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")             # 원본
decp, tabp, idxp, rsp = R.load_rdi(os.path.join(OUT,"RES00.RDI"))  # 패치

FONTS={"COMMON_2D.CHK":"COMMON_2D-한글폰트삽입.CHK",
       "COMMON_2D_ADD.CHK":"COMMON_2D_ADD-한글폰트삽입.CHK"}

# 1) 폰트A 제자리 패치(원본 슬롯 오프셋)
for arc, ff in FONTS.items():
    to=idxo[arc]; loc=R.locate(to["stored"],to["flag"])  # 원본 위치
    rdb, off0, is10 = loc
    kp=os.path.join(OUT, rdb); key=R.file_key(arc)
    with open(rdb,"rb") as f: f.seek(off0); hraw=f.read(32)  # 원본 슬롯 헤더
    header=bytearray(R.crypt(hraw,key))
    body=open(ff,"rb").read()[32:]
    comp=zlib.compress(body,9); new_decsize=R.align_up(len(body),4)
    struct.pack_into("<I",header,0x18,len(comp))
    struct.pack_into("<I",header,0x1C,off0//R.SECTOR)
    need_phys=R.align_up(32+len(comp),R.SECTOR)
    blob=bytearray(need_phys); blob[:32]=header; blob[32:32+len(comp)]=comp
    enc=R.crypt(bytes(blob),key)
    with open(kp,"r+b") as f: f.seek(off0); f.write(enc)
    # RDI(패치본) → 원본 offset + 새 decsize
    rp=rsp + idxp[arc]["i"]*9
    struct.pack_into("<I",decp,rp,to["stored"])
    struct.pack_into("<I",decp,rp+4,new_decsize)
    print(f"  [폰트제자리] {arc} @0x{off0:x} comp={len(comp)}")

# 2) 나머지 재배치 CHK → 원본 RDI로 복원
reverted=0
for name in idxo:
    if name in FONTS: continue
    o=idxo[name]; p=idxp.get(name)
    if p is None: continue
    if o["stored"]!=p["stored"]:  # 재배치됨
        rp=rsp + p["i"]*9
        struct.pack_into("<I",decp,rp,o["stored"])       # 원본 offset
        struct.pack_into("<I",decp,rp+4,o["DEC_SIZE"])   # 원본 decsize
        reverted+=1
print(f"  [재배치복원] 텍스트 CHK {reverted}개 → 원본(일본어)")

R.save_rdi(decp, os.path.join(OUT,"RES00.RDI"))
print("RDI 저장 완료.")

# 검증: 폰트 재독
for arc, ff in FONTS.items():
    to=idxo[arc]; loc=R.locate(to["stored"],to["flag"]); rdb,off0,_=loc
    kp=os.path.join(OUT,rdb); key=R.file_key(arc)
    with open(kp,"rb") as f: f.seek(off0); hraw=f.read(32)
    hdr=R.crypt(hraw,key); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(kp,"rb") as f: f.seek(off0); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key); got=zlib.decompress(d[32:32+clen])
    print(f"  검증 {arc}: {'OK' if got==open(ff,'rb').read()[32:] else '불일치'}")
print("\n완료. repack_out = 폰트A(제자리) + 스캔한글 + 재배치제거. 스톡main과 테스트.")
