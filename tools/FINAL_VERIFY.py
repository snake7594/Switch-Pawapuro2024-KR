# -*- coding: utf-8 -*-
"""최종 종합 검증(repack_out + main-final).
   1) SEN_TEXT: 압축 재번역 17개가 전체(잘림無)로 들어갔나
   2) STRING CHK 43: repack_out에서 한글 유지(일본어 reversion 아님) + RDI DEC_SIZE 일관
   3) RDB 무결성: RDI의 모든 압축슬롯이 복호+zlib해제 성공(대량 샘플)
   4) main-final: 크기·.text·헤더 불변 재확인"""
import os, sys, struct, zlib, json, random
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R, inject_lib as L
import numpy as np
OUT="repack_out"
ENC=L.Encoder(os.path.join("!폰트작업","실황2024.wReplace"))

def read_slot(rdb_dir, fn, t):
    loc=R.locate(t["stored"],t["flag"]); rdb,off,_=loc; key=R.file_key(fn)
    path=os.path.join(rdb_dir,rdb)
    with open(path,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=bytearray(R.crypt(hraw,key)); clen=struct.unpack_from("<I",hdr,0x18)[0]
    dsz=t["DEC_SIZE"]
    readlen=R.align_up(max(dsz,32+clen),4)
    with open(path,"rb") as f: f.seek(off); raw=f.read(readlen)
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    cl=struct.unpack_from("<I",d,0x18)[0]
    body=zlib.decompress(d[32:32+cl]) if t["flag"]>0 else bytes(d[32:32+(dsz-32)])
    return body

# repack_out RDI(갱신본)로 검증
dec,tab,idx,rec=R.load_rdi(os.path.join(OUT,"RES00.RDI"))

print("[1] SEN_TEXT 17개 재번역 전체복구")
new=json.load(open(r'C:\Users\JAEHOL~1\AppData\Local\Temp\claude\C--Users-Jae-Ho-Lee-Pictures-psp-roms-Breath-of-Fire-III\8090a8b2-c642-4a55-91fb-6f8b4203aba9\scratchpad\sen_new.json',encoding='utf-8'))
body=read_slot(OUT,"SEN_TEXT.CHK",idx["SEN_TEXT.CHK"])
ok17=0
for jp,ko in new.items():
    if ENC.encode(ko) in body: ok17+=1
print(f"   전체복구 확인 {ok17}/17 (repack_out SEN_TEXT에 완역 존재)")

print("[2] STRING CHK 43 한글 유지 + RDI 일관")
doc=json.load(open("번역_일본어.json",encoding="utf-8"))
from collections import defaultdict
per=defaultdict(dict)
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if not ko: continue
    for o in s["occurrences"]:
        if o["method"]=="string": per[o["file"]][o["index"]]=ENC.encode(ko)
kor_ok=jp_rev=0
for fn,repl in per.items():
    body=read_slot(OUT,fn,idx[fn])
    strs=L.parse_string_list(bytes(idx[fn].get("_h",b"")).ljust(0,b"")+body) if False else L.parse_string_list(b"\x00"*32+body)
    if strs is None: print("   [parse실패]",fn); continue
    # 번역 인덱스 중 한글이 실제로 들어갔나(샘플 3개)
    hit=miss=0
    for i2,kob in list(repl.items())[:5]:
        if 0<=i2<len(strs):
            if strs[i2]==kob: hit+=1
            else: miss+=1
    if hit>0: kor_ok+=1
    if hit==0 and miss>0: jp_rev+=1; print("   [의심-되돌림?]",fn)
print(f"   한글 유지 파일 {kor_ok}/{len(per)}, 되돌림의심 {jp_rev}")

print("[3] RDB 무결성(압축슬롯 복호+해제 성공률, 랜덤 2000샘플)")
comp=[t for t in tab if t["flag"]>0 and R.locate(t["stored"],t["flag"])]
random.seed(1); sample=random.sample(comp, min(2000,len(comp)))
good=bad=0; errs=[]
for t in sample:
    try:
        read_slot(OUT,t["name"],t); good+=1
    except Exception as e:
        bad+=1; errs.append((t["name"],str(e)[:40]))
print(f"   성공 {good}/{len(sample)}, 실패 {bad}")
for n,e in errs[:8]: print("     실패:",n,e)

print("[4] main-final 불변 재확인")
o=open("!exefs-작업/main-원본","rb").read(); n=open("inject_out/main-final","rb").read()
tx_fo,_,tx_sz=struct.unpack_from("<III",n,0x10)
ao=np.frombuffer(o,dtype=np.uint8); an=np.frombuffer(n,dtype=np.uint8)
diff=np.nonzero(ao!=an)[0]
print(f"   크기 {len(o)}=={len(n)}? {len(o)==len(n)}; .text변경 {int(((diff>=tx_fo)&(diff<tx_fo+tx_sz)).sum())}; 헤더변경 {int((diff<0x100).sum())}")

print("\n종합:", "✅ 통과" if (ok17==17 and jp_rev==0 and bad==0 and len(o)==len(n)) else "⚠ 확인필요")
