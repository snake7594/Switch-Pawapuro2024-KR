# -*- coding: utf-8 -*-
"""repack_out의 COMMON_2D / COMMON_2D_ADD 폰트를 B→A(정상, 이미지 미손상)로 교체.
   폰트 A(root COMMON_2D-한글폰트삽입.CHK / COMMON_2D_ADD-한글폰트삽입.CHK)를
   repack_out RDB 끝에 재배치하고 RDI 갱신. (6.6GB 복사 없음, 수초)
   결과: repack_out = 폰트A + 텍스트  → 스톡 main과 함께 배포해 테스트."""
import os, sys, zlib, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R

OUT="repack_out"
FONTS={  # 아카이브명 -> 폰트A 파일(정상)
    "COMMON_2D.CHK":     "COMMON_2D-한글폰트삽입.CHK",
    "COMMON_2D_ADD.CHK": "COMMON_2D_ADD-한글폰트삽입.CHK",
}
dec, table, idx, rec_start = R.load_rdi(os.path.join(OUT,"RES00.RDI"))
print(f"repack_out RDI 로드, 항목 {len(table)}")

for arc, ff in FONTS.items():
    t=idx[arc]; loc=R.locate(t["stored"],t["flag"])
    rdb_name, off_cur, is10 = loc
    kp=os.path.join(OUT, rdb_name); key=R.file_key(arc)
    # 현재 슬롯 헤더(권위) 확보
    with open(kp,"rb") as f: f.seek(off_cur); hraw=f.read(32)
    header=bytearray(R.crypt(hraw,key))
    body=open(ff,"rb").read()[32:]
    comp=zlib.compress(body,9)
    new_decsize=R.align_up(len(body),4)
    struct.pack_into("<I",header,0x18,len(comp))
    # 끝에 재배치
    with open(kp,"r+b") as f:
        f.seek(0,2); end=f.tell()
        new_local=R.align_up(end, R.SECTOR)
        new_stored, sect = R.stored_from_local(new_local, is10)
        struct.pack_into("<I",header,0x1C,sect)
        phys=R.align_up(max(new_decsize,32+len(comp)), R.SECTOR)
        blob=bytearray(phys); blob[:32]=header; blob[32:32+len(comp)]=comp
        enc=R.crypt(bytes(blob),key)
        f.seek(new_local); f.write(enc)
    # RDI 갱신
    rp=rec_start + t["i"]*9
    struct.pack_into("<I",dec,rp,new_stored)
    struct.pack_into("<I",dec,rp+4,new_decsize)
    print(f"  {arc}: 폰트A 재배치 @0x{new_local:x} ({rdb_name}) comp={len(comp)} decsize={new_decsize}")

R.save_rdi(dec, os.path.join(OUT,"RES00.RDI"))
print("RDI 갱신 완료")

# 검증: 재독
print("검증:")
for arc, ff in FONTS.items():
    t=idx[arc]; loc=R.locate(struct.unpack_from('<I',dec,rec_start+t['i']*9)[0], t['flag'])
    rdb_name, off, is10 = loc
    kp=os.path.join(OUT, rdb_name); key=R.file_key(arc)
    with open(kp,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=R.crypt(hraw,key); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(kp,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key); got=zlib.decompress(d[32:32+clen])
    src=open(ff,"rb").read()[32:]
    print(f"  {arc}: {'OK 일치' if got==src else '불일치!'}")
print("\n완료. repack_out = 폰트A + 텍스트. 스톡 main과 함께 배포해 테스트.")
