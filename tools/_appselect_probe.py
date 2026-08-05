# -*- coding: utf-8 -*-
"""APPSELECT 불일치 원인: 원본RDB 슬롯 vs RES_추출원본 vs repack_out 3-way 비교."""
import os, sys, struct, zlib, hashlib
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R

deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")
fn="APPSELECT.CHK"
t=idxo[fn]; loc=R.locate(t["stored"],t["flag"])
rdb,off,is10=loc
key=R.file_key(fn)
print(f"{fn}: {rdb} off=0x{off:x} flag={t['flag']:#x} DEC_SIZE={t['DEC_SIZE']}")

def slot_body(path):
    with open(path,"rb") as f:
        f.seek(off); hraw=f.read(32)
    hdr=R.crypt(hraw,key); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(path,"rb") as f:
        f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    if t["flag"]>0:
        try: return zlib.decompress(d[32:32+clen]), clen, hdr
        except Exception as e: return None, clen, hdr
    return d[32:], None, hdr

for label,path in (("원본RDB",rdb), ("repack_out",os.path.join("repack_out",rdb))):
    body,clen,hdr=slot_body(path)
    h=hashlib.md5(body).hexdigest()[:12] if body else "죽음"
    print(f"  {label}: clen={clen} body_len={len(body) if body else 0} md5={h}")

src=open(os.path.join("RES_추출원본",fn),"rb").read()[32:]
print(f"  RES_추출원본: body_len={len(src)} md5={hashlib.md5(src).hexdigest()[:12]}")
inj=open(os.path.join("repack_in",fn),"rb").read()[32:]
print(f"  repack_in   : body_len={len(inj)} md5={hashlib.md5(inj).hexdigest()[:12]}")

# 원본RDB 슬롯 바디와 두 파일 비교
body,_,_=slot_body(rdb)
if body:
    print(f"\n  원본RDB슬롯 == RES_추출원본 ? {body[:len(src)]==src and len(body)==len(src)}")
    print(f"  원본RDB슬롯 == repack_in   ? {body[:len(inj)]==inj and len(body)==len(inj)}")
    if len(body)==len(src) and body!=src:
        nd=[i for i in range(len(src)) if body[i]!=src[i]][:10]
        print(f"  다른 위치(앞 10): {[hex(i) for i in nd]}")
        for i in nd[:3]:
            print(f"    0x{i:x}: RDB={body[i]:02x} 추출원본={src[i]:02x}")
