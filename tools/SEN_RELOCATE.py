# -*- coding: utf-8 -*-
"""SEN_TEXT.CHK 재배치 주입 — 선수 소개문 전체 번역(슬랙 포함, 잘림 0).
   in-place 불가(Korean comp 77406 > gap 75264)라 REPACK 재배치 경로를 미러링:
     진짜베이스 body에 모든 scan 번역을 patch_at_offset(슬랙=레코드 패딩, 안전)로 적용 → body 크기 불변.
     comp를 repack_out RES00.RDB '끝(섹터정렬)'에 자족 슬롯으로 추가, RDI(OFFSET·DEC_SIZE) 갱신.
     구 슬롯은 고아(미사용)로 남김. 게임은 RDI(이름→OFFSET)로 접근하므로 재배치 투명.
   기록 후 새 오프셋에서 재독 검증."""
import os, sys, struct, zlib, json
sys.stdout.reconfigure(encoding='utf-8')
ROOT="C:/Users/Jae Ho Lee/Desktop/z/실황2024"; os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R, inject_lib as L
ENC=L.Encoder(os.path.join("!폰트작업","실황2024.wReplace"))
OUT="repack_out"; FN="SEN_TEXT.CHK"; SECTOR=R.SECTOR

dec,tab,idx,rec=R.load_rdi(os.path.join(OUT,"RES00.RDI"))
t=idx[FN]; loc=R.locate(t["stored"],t["flag"]); rdb,off0,is10=loc; key=R.file_key(FN)
print(f"SEN_TEXT 소재: {rdb} (is10={is10}) local off 0x{off0:X}")

# 진짜 베이스 body(root RDB)
with open(rdb,"rb") as f: f.seek(off0); hraw=f.read(32)
hdr=bytearray(R.crypt(hraw,key)); clen=struct.unpack_from("<I",hdr,0x18)[0]
with open(rdb,"rb") as f: f.seek(off0); raw=f.read(R.align_up(32+clen,4))
if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
body=bytearray(zlib.decompress(R.crypt(raw,key)[32:32+clen]))
orig_len=len(body)

# 모든 SEN scan 번역 적용(슬랙 사용)
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
    jl=len(jpb); st=0
    while True:
        i=body.find(jpb,st)
        if i<0: break
        pre=(i==0) or (body[i-1]==0); post=(i+jl>=len(body)) or (body[i+jl]==0)
        if pre and post:
            if L.patch_at_offset(body,i,jl,kob): trunc+=1
            hit+=1
        st=i+1
assert len(body)==orig_len, "body 크기 변함(제자리 위반)"
print(f"번역 적용: 치환 {hit}, 슬랙후에도 잘림 {trunc}")

# 재배치: repack_out RES00.RDB 끝(섹터정렬)에 추가
comp=zlib.compress(bytes(body),9)
new_decsize=R.align_up(len(body),4)
outpath=os.path.join(OUT,rdb)
new_local=R.align_up(os.path.getsize(outpath), SECTOR)
new_stored,sect=R.stored_from_local(new_local, is10)
struct.pack_into("<I",hdr,0x18,len(comp))
struct.pack_into("<I",hdr,0x1C,sect)
phys=R.align_up(max(new_decsize,32+len(comp)),SECTOR)
blob=bytearray(phys); blob[:32]=hdr; blob[32:32+len(comp)]=comp
enc=R.crypt(bytes(blob),key)
with open(outpath,"r+b") as f: f.seek(new_local); f.write(enc)
# RDI 갱신
rp=rec+t["i"]*9
struct.pack_into("<I",dec,rp,new_stored)
struct.pack_into("<I",dec,rp+4,new_decsize)
R.save_rdi(dec, os.path.join(OUT,"RES00.RDI"))
print(f"재배치: off 0x{off0:X}→0x{new_local:X} (sector {sect}), comp {len(comp)}, decsize {new_decsize}, RDB +{phys}B")

# 재독 검증(새 오프셋)
with open(outpath,"rb") as f: f.seek(new_local); raw2=f.read(new_decsize)
if len(raw2)%4: raw2+=b"\x00"*(4-len(raw2)%4)
d2=R.crypt(raw2,key); cl2=struct.unpack_from("<I",d2,0x18)[0]
body2=zlib.decompress(d2[32:32+cl2])
new=json.load(open(r'C:\Users\JAEHOL~1\AppData\Local\Temp\claude\C--Users-Jae-Ho-Lee-Pictures-psp-roms-Breath-of-Fire-III\8090a8b2-c642-4a55-91fb-6f8b4203aba9\scratchpad\sen_new.json',encoding='utf-8'))
ok=sum(1 for jp,ko in new.items() if ENC.encode(ko) in body2)
kor=sum(1 for jpb,kob in pairs if kob in body2)
print(f"검증: body 일치 {body2==bytes(body)}, 완역17 {ok}/17, 전체 한글 매칭 {kor}/{len(pairs)}", "✅" if ok==17 and body2==bytes(body) else "⚠")
