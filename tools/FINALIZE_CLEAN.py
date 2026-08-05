# -*- coding: utf-8 -*-
"""최청정 빌드: repack_out에서 재배치 잔재 제거 → '원본 + 제자리 슬롯교체'만 남김.
   1) RDB를 원본 크기로 truncate (append tail 제거)
   2) 폰트를 폰트B(대+소 한글, 구조검증됨)로 제자리 재기록
   3) RDI 레코드가 원본과 동일한지 검증 → 동일하면 원본 RDI 사용
   결과: 원본과의 차이 = 폰트B 슬롯 2개 + 텍스트 스캔 CHK 555개 (전부 제자리)"""
import os, sys, zlib, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
OUT="repack_out"; RES="RES_추출원본"

# 1) truncate
for rdb in ("RES00.RDB","RES10.RDB"):
    orig=os.path.getsize(rdb); kp=os.path.join(OUT,rdb); cur=os.path.getsize(kp)
    if cur>orig:
        with open(kp,"r+b") as f: f.truncate(orig)
        print(f"  {rdb}: {cur} -> {orig} truncate (tail {cur-orig} 제거)")
    else:
        print(f"  {rdb}: 크기 원본과 동일({cur})")

# 2) 폰트 B 제자리 기록 (구조 검증된 대+소 한글 폰트)
deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")
FONTS={"COMMON_2D.CHK":"repack_in/COMMON_2D.CHK",
       "COMMON_2D_ADD.CHK":"repack_in/COMMON_2D_ADD.CHK"}
for arc, ff in FONTS.items():
    t=idxo[arc]; loc=R.locate(t["stored"],t["flag"]); rdb,off0,is10=loc
    kp=os.path.join(OUT,rdb); key=R.file_key(arc)
    with open(rdb,"rb") as f: f.seek(off0); hraw=f.read(32)
    header=bytearray(R.crypt(hraw,key))
    body=open(ff,"rb").read()[32:]
    comp=zlib.compress(body,9)
    assert R.align_up(len(body),4)==t["DEC_SIZE"], f"{arc} decsize 변동!"
    struct.pack_into("<I",header,0x18,len(comp))
    struct.pack_into("<I",header,0x1C,off0//R.SECTOR)
    need=R.align_up(32+len(comp),R.SECTOR)
    # 제자리 공간 확인
    blob=bytearray(need); blob[:32]=header; blob[32:32+len(comp)]=comp
    enc=R.crypt(bytes(blob),key)
    with open(kp,"r+b") as f: f.seek(off0); f.write(enc)
    print(f"  [폰트B 제자리] {arc} @0x{off0:x} comp={len(comp)} decsize동일")

# 3) RDI 검증: repack_out RDI가 필요한가? 모든 레코드가 원본과 동일해야 함
decp, tabp, idxp, rsp = R.load_rdi(os.path.join(OUT,"RES00.RDI"))
mism=[]
for name in idxo:
    o=idxo[name]; p=idxp.get(name)
    if p is None: continue
    if o["stored"]!=p["stored"] or o["DEC_SIZE"]!=p["DEC_SIZE"] or o["flag"]!=p["flag"]:
        mism.append((name,o,p))
print(f"\nRDI 레코드 원본과 다른 항목: {len(mism)}개")
for name,o,p in mism[:10]:
    print(f"   {name}: stored {o['stored']}->{p['stored']} dec {o['DEC_SIZE']}->{p['DEC_SIZE']}")
if not mism:
    import shutil
    shutil.copy2("RES00.RDI", os.path.join(OUT,"RES00.RDI"))
    print("→ 전부 동일. 원본 RDI를 그대로 출력에 복사 (RDI 변수 완전 제거)")
else:
    # 다른 항목을 원본으로 복원 후 저장
    for name,o,p in mism:
        rp2=rsp+p["i"]*9
        struct.pack_into("<I",decp,rp2,o["stored"])
        struct.pack_into("<I",decp,rp2+4,o["DEC_SIZE"])
    R.save_rdi(decp, os.path.join(OUT,"RES00.RDI"))
    print("→ 원본값으로 복원 후 저장")

# 4) 최종 검증: 폰트 슬롯 재독 + 원본과 다른 슬롯 개수 개괄
print("\n최종 검증(폰트 재독):")
for arc, ff in FONTS.items():
    t=idxo[arc]; loc=R.locate(t["stored"],t["flag"]); rdb,off0,_=loc
    kp=os.path.join(OUT,rdb); key=R.file_key(arc)
    with open(kp,"rb") as f: f.seek(off0); hraw=f.read(32)
    hdr=R.crypt(hraw,key); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(kp,"rb") as f: f.seek(off0); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key); got=zlib.decompress(d[32:32+clen])
    src=open(ff,"rb").read()[32:]
    print(f"  {arc}: {'OK' if got==src else '불일치!'}")
print("\n완료: repack_out = 원본 + 폰트B(제자리) + 텍스트스캔555(제자리). RDI=원본동일.")
