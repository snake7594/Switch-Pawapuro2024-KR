# -*- coding: utf-8 -*-
"""repack_out 무결성 검증: 폰트/텍스트 슬롯을 repack_out에서 재독해 편집본과 일치하는지."""
import os, sys, zlib, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT=os.path.dirname(os.path.abspath(__file__)); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R

OUT="repack_out"
for f in ("RES00.RDB","RES10.RDB","RES00.RDI"):
    p=os.path.join(OUT,f)
    print(f"  {f}: {'있음 '+format(os.path.getsize(p),',')+'B' if os.path.isfile(p) else '없음!'}")

dec, table, idx, rec_start = R.load_rdi(os.path.join(OUT,"RES00.RDI"))
print(f"RDI 항목 {len(table)}개")

def read_body(arc):
    """repack_out에서 arc 슬롯을 재독해 압축해제 본문 반환."""
    t=idx[arc]; loc=R.locate(t["stored"],t["flag"])
    if loc is None: return None,"ID타입"
    rdb=os.path.join(OUT,loc[0]); key=R.file_key(arc); off=loc[1]
    with open(rdb,"rb") as f:
        f.seek(off); hraw=f.read(32)
    hdr=R.crypt(hraw,key); clen=struct.unpack_from("<I",hdr,0x18)[0]
    if t["flag"]>0:
        slot_len=R.align_up(32+clen,4)
        with open(rdb,"rb") as f: f.seek(off); raw=f.read(slot_len)
        if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
        d=R.crypt(raw,key)
        try: return zlib.decompress(d[32:32+clen]),"OK"
        except Exception as e: return None,f"zlib실패:{e}"
    else:
        slot_len=t["DEC_SIZE"]
        with open(rdb,"rb") as f: f.seek(off); raw=f.read(slot_len)
        if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
        d=R.crypt(raw,key)
        return d[32:32+(slot_len-32)],"OK(flag0)"

def compare(arc, srcpath):
    body,st=read_body(arc)
    if body is None: return f"{arc}: {st}"
    src=open(srcpath,"rb").read()[32:]
    match=(body[:len(src)]==src and len(body)==len(src))
    return f"{arc}: {st}  편집본일치={match} (본문 {len(body)} vs {len(src)})"

print("\n=== 폰트 슬롯 ===")
print("  "+compare("COMMON_2D.CHK","COMMON_2D-한글폰트삽입.CHK"))
print("  "+compare("COMMON_2D_ADD.CHK","COMMON_2D_ADD-한글폰트삽입.CHK"))

print("\n=== 텍스트 CHK 샘플 (repack_in 편집본과 비교) ===")
samples=[fn for fn in sorted(os.listdir("repack_in")) if fn not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK") and fn in idx][:5]
for fn in samples:
    print("  "+compare(fn, os.path.join("repack_in",fn)))
