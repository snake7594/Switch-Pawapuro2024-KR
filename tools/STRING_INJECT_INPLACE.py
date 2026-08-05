# -*- coding: utf-8 -*-
"""43개 STRING CHK 전체복구를 '작동 중인 repack_out'에 제자리 주입(재배치 0).
   - base = ROOT RDB 슬롯(진짜 베이스=원본 일본어). rebuild_string_chk로 전체 한글(가변길이) body 생성.
   - 압축본이 gap에 들어감(측정 완료: 43/43 제자리). REPACK의 제자리 경로를 그대로 미러링:
       헤더[0x18]=comp크기, [0x1C]=로컬섹터(불변), 슬롯=헤더+comp(4정렬) crypt → repack_out RDB 제자리 기록.
       RDI(DEC_SIZE)=align_up(len(new_body),4)로 갱신, OFFSET 불변.
   - scan/font(이미 repack_out에 반영)와 stale repack_in은 건드리지 않음. repack_out/RES00.RDI 갱신.
   - 기록 후 재독 검증(복호+해제+parse 일치)."""
import os, sys, struct, zlib, json, bisect
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
import inject_lib as L
ENC=L.Encoder(os.path.join("!폰트작업","실황2024.wReplace"))
OUTDIR="repack_out"
SECTOR=R.SECTOR

# RDI: repack_out 것(root와 동일)을 로드해 수정
dec,tab,idx,rec_start=R.load_rdi(os.path.join(OUTDIR,"RES00.RDI"))
laid={"RES00.RDB":[], "RES10.RDB":[]}
for t in tab:
    loc=R.locate(t["stored"],t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
# gap은 ORIGINAL 레이아웃(=repack_out 레이아웃, 재배치 없었음) 기준
osz={k:os.path.getsize(k) for k in laid}   # root 크기(=repack_out 크기 동일)
def gap_of(rdb,off):
    a=laid[rdb]; j=bisect.bisect_right(a,off)
    return (a[j] if j<len(a) else osz[rdb])-off

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
per=defaultdict(dict)
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if not ko: continue
    for o in s["occurrences"]:
        if o["method"]=="string": per[o["file"]][o["index"]]=ENC.encode(ko)

def read_true_body(fn):
    """ROOT RDB(진짜 베이스)에서 헤더32(복호)+body(해제)."""
    t=idx[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,is10=loc; key=R.file_key(fn)
    with open(rdb,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=bytearray(R.crypt(hraw,key)); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(rdb,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    body=zlib.decompress(d[32:32+clen]) if t["flag"]>0 else bytes(d[32:32+(t["DEC_SIZE"]-32)])
    return t,rdb,off,is10,key,hdr,body

fh={}
report=[]
done=trunc_skip=0
try:
    for fn,repl in sorted(per.items()):
        if fn not in idx: print("  [RDI無]",fn); continue
        t,rdb,off,is10,key,hdr,body=read_true_body(fn)
        extracted=bytes(hdr)+body
        strs=L.parse_string_list(extracted)
        if strs is None: print("  [STRING無]",fn); continue
        new=list(strs)
        for i2,kob in repl.items():
            if 0<=i2<len(new): new[i2]=kob
        outb=L.rebuild_string_chk(extracted,new)
        new_body=outb[32:]
        if t["flag"]>0:
            comp=zlib.compress(new_body,9)
            new_decsize=R.align_up(len(new_body),4)
        else:  # flag=0 비압축: body 원본 그대로, DEC_SIZE=슬롯길이(헤더32+본문)
            comp=new_body
            new_decsize=R.align_up(32+len(new_body),4)
        need_phys=R.align_up(32+len(comp),4)
        g=gap_of(rdb,off)
        if need_phys>g:
            print(f"  [gap부족 건너뜀] {fn} need {need_phys} > gap {g}"); trunc_skip+=1; continue
        struct.pack_into("<I",hdr,0x18,len(comp) if t["flag"]>0 else new_decsize)
        struct.pack_into("<I",hdr,0x1C,off//SECTOR)  # 불변(제자리)
        blob=bytearray(need_phys); blob[:32]=hdr; blob[32:32+len(comp)]=comp
        enc=R.crypt(bytes(blob),key)
        if rdb not in fh: fh[rdb]=open(os.path.join(OUTDIR,rdb),"r+b")
        fh[rdb].seek(off); fh[rdb].write(enc)
        # RDI: DEC_SIZE 갱신, OFFSET 불변
        rp=rec_start+t["i"]*9
        struct.pack_into("<I",dec,rp+4,new_decsize)
        report.append((fn,rdb,off,key,new_decsize,len(comp),new_body,t["flag"]))
        done+=1
finally:
    for f in fh.values(): f.close()

# RDI 저장
R.save_rdi(dec, os.path.join(OUTDIR,"RES00.RDI"))
print(f"주입 {done}개, gap부족 건너뜀 {trunc_skip}개. RDI 갱신.")

# 재독 검증
print("검증(재독):")
ok=True
for fn,rdb,off,key,decsz,clen,nb,flag in report:
    with open(os.path.join(OUTDIR,rdb),"rb") as f: f.seek(off); raw=f.read(decsz)
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    cl=struct.unpack_from("<I",d,0x18)[0]
    chk=zlib.decompress(d[32:32+cl]) if flag>0 else d[32:32+(decsz-32)]
    good=(chk[:len(nb)]==nb and L.parse_string_list(bytes(d[:32])+chk) is not None)
    ok=ok and good
    if not good: print("   [불일치]",fn)
print("검증:", "전체 통과 ✅" if ok else "[실패 있음]")
if not ok: raise SystemExit("검증 실패 — repack_out 사용 금지")
