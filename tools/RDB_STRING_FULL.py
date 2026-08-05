# -*- coding: utf-8 -*-
"""RDB STRING CHK 전체복구(가변길이) — 진짜 베이스(root RDB) 기준.
   inject_all은 RES_추출원본(버전 불일치)에서 읽어 STRING CHK가 깨졌음 → 여기선 root RDB 슬롯을 base로.
   각 STRING CHK: 슬롯 복호→디컴프→body. extracted=헤더32+body 로 만들어 parse/rebuild_string_chk 적용.
   전체 한글(가변길이)로 재구성 → repack_in/FN.CHK 기록. gap 적합여부(제자리 가능/재배치 필요) 미리 측정.
   이후 REPACK_AUTO 실행 시: gap 여유면 제자리(재배치X), 큰 것만 재배치. RDI는 REPACK가 갱신.
   --check : 파일 안 쓰고 gap 적합만 측정."""
import os, sys, struct, zlib, json, bisect
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
import inject_lib as L
CHECK = "--check" in sys.argv
ENC=L.Encoder(os.path.join("!폰트작업","실황2024.wReplace"))
OUT="repack_in"

deco,tabo,idxo,rso=R.load_rdi("RES00.RDI")

# 레이아웃(제자리 gap 계산용)
laid={"RES00.RDB":[], "RES10.RDB":[]}
for t in tabo:
    loc=R.locate(t["stored"],t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
osz={k:(os.path.getsize(k) if os.path.isfile(k) else 0) for k in laid}
def gap_of(rdb,off):
    a=laid[rdb]; j=bisect.bisect_right(a,off)
    return (a[j] if j<len(a) else osz[rdb])-off

# STRING 번역 수집
doc=json.load(open("번역_일본어.json",encoding="utf-8"))
per=defaultdict(dict)   # file -> {index: kob}
miss=set()
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if not ko: continue
    for o in s["occurrences"]:
        if o["method"]=="string":
            miss.update(ENC.covers(ko))
            per[o["file"]][o["index"]]=ENC.encode(ko)
print(f"STRING CHK 파일 {len(per)}개, 폰트미지원 음절 {len(miss)}종")

def true_slot(fn):
    t=idxo[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,is10=loc; key=R.file_key(fn)
    with open(rdb,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=bytes(R.crypt(hraw,key)); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(rdb,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    body=zlib.decompress(d[32:32+clen]) if t["flag"]>0 else bytes(d[32:32+(t["DEC_SIZE"]-32)])
    return t,rdb,off,key,hdr,body

fit=reloc=badrt=0; reloc_files=[]
if not CHECK: os.makedirs(OUT,exist_ok=True)
for fn,repl in sorted(per.items()):
    if fn not in idxo: print("  [RDI無]",fn); continue
    t,rdb,off,key,hdr,body=true_slot(fn)
    extracted=hdr+body                         # rebuild_string_chk 전제(헤더32+body, @0x2C=body0x0C)
    strs=L.parse_string_list(extracted)
    if strs is None: print("  [STRING無]",fn); continue
    # 라운드트립 자기검증: 원본 strings로 rebuild → body 파싱 동일?
    rt=L.rebuild_string_chk(extracted, list(strs))
    if L.parse_string_list(rt)!=strs: badrt+=1; print("  [RT실패]",fn); continue
    new=list(strs)
    for idx,kob in repl.items():
        if 0<=idx<len(new): new[idx]=kob
    outb=L.rebuild_string_chk(extracted, new)
    newbody=outb[32:]
    comp=zlib.compress(newbody,9); need=R.align_up(32+len(comp),4)
    g=gap_of(rdb,off)
    if need<=g: fit+=1
    else: reloc+=1; reloc_files.append((fn,need,g))
    if not CHECK: open(os.path.join(OUT,fn),"wb").write(outb)

print(f"\ngap 제자리가능 {fit}, 재배치필요 {reloc}, 라운드트립실패 {badrt}")
if reloc_files:
    print("재배치 대상:")
    for fn,need,g in reloc_files[:20]: print(f"   {fn}: 필요 {need} > gap {g}")
if miss: print(f"미지원 음절: {''.join(sorted(miss))}")
print("완료" if not CHECK else "측정만(파일 미기록)")
