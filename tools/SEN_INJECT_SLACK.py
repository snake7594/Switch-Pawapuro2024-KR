# -*- coding: utf-8 -*-
"""SEN_TEXT.CHK만 슬랙 사용(patch_at_offset)으로 재주입 → 긴 소개문 전체복구.
   SEN_TEXT 레코드=[ID][UTF-8텍스트][0패딩]. 패딩(슬랙)은 이 레코드의 자유공간이라 안전.
   진짜 베이스(root RDB) body에서 각 일본어(NUL경계) 탐색 → patch_at_offset(뒤 NUL슬랙까지, 종료NUL 1개 유지).
   body 크기 불변(제자리) → 재압축이 gap에 들어감. repack_out 제자리 기록, RDI 불변. 재독 검증."""
import os, sys, struct, zlib, json, bisect
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R, inject_lib as L
ENC=L.Encoder(os.path.join("!폰트작업","실황2024.wReplace"))
OUT="repack_out"; FN="SEN_TEXT.CHK"

dec,tab,idx,rec=R.load_rdi("RES00.RDI")
laid={"RES00.RDB":[], "RES10.RDB":[]}
for t in tab:
    loc=R.locate(t["stored"],t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
osz={k:os.path.getsize(k) for k in laid}
def gap_of(rdb,off):
    a=laid[rdb]; j=bisect.bisect_right(a,off)
    return (a[j] if j<len(a) else osz[rdb])-off

t=idx[FN]; loc=R.locate(t["stored"],t["flag"]); rdb,off,_=loc; key=R.file_key(FN)
with open(rdb,"rb") as f: f.seek(off); hraw=f.read(32)
hdr=bytearray(R.crypt(hraw,key)); clen=struct.unpack_from("<I",hdr,0x18)[0]
with open(rdb,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
body=bytearray(zlib.decompress(R.crypt(raw,key)[32:32+clen]))

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
pairs=[]
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if not ko: continue
    for o in s["occurrences"]:
        if o["method"]=="scan" and o["file"]==FN:
            pairs.append((s["jp"].encode("utf-8"), ENC.encode(ko)))
pairs=list(dict.fromkeys(pairs))

hit=trunc=0
for jpb,kob in pairs:
    jl=len(jpb); start=0
    while True:
        i=body.find(jpb,start)
        if i<0: break
        pre=(i==0) or (body[i-1]==0)
        post=(i+jl>=len(body)) or (body[i+jl]==0)
        if pre and post:
            if L.patch_at_offset(body, i, jl, kob): trunc+=1
            hit+=1
        start=i+1

comp=zlib.compress(bytes(body),9); need=R.align_up(32+len(comp),4)
g=gap_of(rdb,off)
assert need<=g, f"gap 부족 {need}>{g}"
new_decsize=R.align_up(len(body),4)  # body 크기 불변이지만 규칙대로
struct.pack_into("<I",hdr,0x18,len(comp)); struct.pack_into("<I",hdr,0x1C,off//R.SECTOR)
blob=bytearray(need); blob[:32]=hdr; blob[32:32+len(comp)]=comp
enc=R.crypt(bytes(blob),key)
with open(os.path.join(OUT,rdb),"r+b") as f: f.seek(off); f.write(enc)
print(f"SEN_TEXT 슬랙 재주입: 치환 {hit}, 잘림(슬랙후에도) {trunc}")

# RDI DEC_SIZE (body 크기 동일이므로 원래값과 같지만 규칙 준수해 갱신)
rp=rec+t["i"]*9; struct.pack_into("<I",dec,rp+4,new_decsize)
R.save_rdi(dec, os.path.join(OUT,"RES00.RDI"))

# 재독 검증: 17개 완역 존재
with open(os.path.join(OUT,rdb),"rb") as f: f.seek(off); raw2=f.read(new_decsize)
if len(raw2)%4: raw2+=b"\x00"*(4-len(raw2)%4)
d2=R.crypt(raw2,key); cl2=struct.unpack_from("<I",d2,0x18)[0]
body2=zlib.decompress(d2[32:32+cl2])
new=json.load(open(r'C:\Users\JAEHOL~1\AppData\Local\Temp\claude\C--Users-Jae-Ho-Lee-Pictures-psp-roms-Breath-of-Fire-III\8090a8b2-c642-4a55-91fb-6f8b4203aba9\scratchpad\sen_new.json',encoding='utf-8'))
ok=sum(1 for jp,ko in new.items() if ENC.encode(ko) in body2)
print(f"검증: 17개 완역 존재 {ok}/17", "✅" if ok==17 else "⚠")
