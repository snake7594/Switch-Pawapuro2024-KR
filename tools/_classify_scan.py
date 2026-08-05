# -*- coding: utf-8 -*-
"""549 스캔 CHK 위험도 분류: NUL구분 UTF-8 문자열 외 '바이너리' 비율.
   순수 문자열 테이블(바이너리≈0)=안전 / 바이너리 높음=스크립트/데이터=위험(포인터 오인)."""
import os, sys, struct, zlib
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
RES="RES_추출원본"
deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")

def true_body(fn):
    t=idxo[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,_=loc; key=R.file_key(fn)
    with open(rdb,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=R.crypt(hraw,key); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(rdb,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    return zlib.decompress(d[32:32+clen]) if t["flag"]>0 else bytes(d[32:32+(t["DEC_SIZE"]-32)])

def is_text_byte(b):
    return b==0x09 or b==0x0a or b==0x0d or (0x20<=b<=0x7e)

def score(body):
    """NUL/ASCII텍스트/UTF-8연속(0x80-0xBF,0xC0-0xEF) = '텍스트류', 그 외 = 바이너리."""
    n=len(body); binc=0
    for b in body:
        if b==0 or is_text_byte(b) or (0x80<=b<=0xef): continue
        binc+=1   # 0xf0-0xff 및 제어문자 등
    return binc, n

files=[fn for fn in os.listdir("repack_in") if fn.endswith(".CHK") and fn not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")]
targets=[]
for fn in files:
    o=os.path.join(RES,fn)
    if not os.path.isfile(o) or fn not in idxo: continue
    ob=open(o,'rb').read(); kb=open(os.path.join("repack_in",fn),'rb').read()
    if len(ob)==len(kb) and ob.find(b'NX  SUR ')<0 and ob!=kb:
        targets.append(fn)

rows=[]
for fn in targets:
    body=true_body(fn)
    binc,n=score(body)
    rows.append((fn,n,binc,binc/max(1,n)))
rows.sort(key=lambda r:-r[3])
print(f"대상 {len(rows)}개. 바이너리비율 높은순 상위 40 (위험):")
for fn,n,binc,frac in rows[:40]:
    print(f"  {fn:30s} size={n:>8} bin={binc:>8} ({frac*100:5.1f}%)")
print("\n바이너리비율 5% 이상:", sum(1 for r in rows if r[3]>=0.05))
print("1% 이상:", sum(1 for r in rows if r[3]>=0.01))
print("0.1% 이상:", sum(1 for r in rows if r[3]>=0.001))
import json
json.dump([r[0] for r in rows if r[3]>=0.01], open("_risky_scan.json","w",encoding="utf-8"), ensure_ascii=False)
print("위험(≥1%) 목록 → _risky_scan.json")
