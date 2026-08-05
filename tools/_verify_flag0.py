# -*- coding: utf-8 -*-
"""repack_out의 주입된 flag=0 CHK들이 온전히 재독되는지 검증(멈춤 후보인 DEC_SIZE 32-부족 버그 탐지).
   + 주입된 모든 CHK를 병렬로 재독 대조(선택)."""
import os, sys, zlib, struct
from concurrent.futures import ProcessPoolExecutor
sys.stdout.reconfigure(encoding='utf-8')
ROOT=os.path.dirname(os.path.abspath(__file__)); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R

OUT="repack_out"
dec, table, idx, rec_start = R.load_rdi(os.path.join(OUT,"RES00.RDI"))

# repack_in 에 있는(=주입된) CHK 목록
injected=[fn for fn in os.listdir("repack_in") if os.path.isfile(os.path.join("repack_in",fn)) and fn in idx]
print(f"주입된 CHK {len(injected)}개")

def check(fn):
    t=idx[fn]; loc=R.locate(t["stored"],t["flag"])
    if loc is None: return (fn,"ID타입",False,t["flag"])
    rdb=os.path.join(OUT,loc[0]); key=R.file_key(fn); off=loc[1]
    try:
        with open(rdb,"rb") as f:
            f.seek(off); hraw=f.read(32)
        hdr=R.crypt(hraw,key); clen=struct.unpack_from("<I",hdr,0x18)[0]
        edited=open(os.path.join("repack_in",fn),"rb").read()[32:]
        if t["flag"]>0:
            slot=R.align_up(32+clen,4)
            with open(rdb,"rb") as f: f.seek(off); raw=f.read(slot)
            if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
            d=R.crypt(raw,key); body=zlib.decompress(d[32:32+clen])
        else:
            slot=t["DEC_SIZE"]
            with open(rdb,"rb") as f: f.seek(off); raw=f.read(slot)
            if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
            d=R.crypt(raw,key); body=d[32:32+(slot-32)]
        ok = body[:len(edited)]==edited and len(body)==len(edited)
        return (fn,"OK" if ok else "불일치",ok,t["flag"])
    except Exception as e:
        return (fn,f"오류:{e}",False,t["flag"])

# flag=0 우선 전수 + 나머지 병렬
if __name__=="__main__":
    results=[]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for r in ex.map(check, injected, chunksize=16):
            results.append(r)
    bad=[r for r in results if not r[2]]
    f0=[r for r in results if r[3]==0]
    f0bad=[r for r in f0 if not r[2]]
    print(f"전체 {len(results)}  통과 {len(results)-len(bad)}  실패 {len(bad)}")
    print(f"flag=0 항목 {len(f0)}  그중 실패 {len(f0bad)}")
    for r in bad[:20]:
        print(f"   [실패] {r[0]} flag={r[3]:#x} : {r[1]}")
    print("\n결론:", "repack_out 온전 ✅ (exe 격리 테스트에 사용 가능)" if not bad else "repack_out에 손상 CHK 있음 — 재빌드 필요")
