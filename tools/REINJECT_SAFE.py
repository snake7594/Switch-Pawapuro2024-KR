# -*- coding: utf-8 -*-
"""안전 재주입 v2 — 구조 손상 0 목표.
   REINJECT_TRUE_BASE의 두 위험 제거:
   (A) 슬랙 미소비: 한글을 '원본 일본어 문자열 길이 내'에만 기록(초과분 UTF-8경계 잘림). 문자열 밖 절대 안 건드림.
   (B) 양쪽 NUL 경계 매칭: 앞바이트=NUL(또는 본문시작) & 뒤바이트=NUL 인 '진짜 NUL구분 문자열'만 치환.
   대상 = 크기불변·이미지없음 텍스트 CHK 549 (진짜 베이스=root RDB 슬롯).
   repack_out 제자리 갱신, RDI 불변. 미매칭/공간부족은 원본복원."""
import os, sys, struct, zlib, json, bisect
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R
import inject_lib as L
RES="RES_추출원본"; OUT="repack_out"

deco, tabo, idxo, rso = R.load_rdi("RES00.RDI")
ENC=L.Encoder(os.path.join("!폰트작업","실황2024.wReplace"))

laid={"RES00.RDB":[], "RES10.RDB":[]}
for t0 in tabo:
    loc0=R.locate(t0["stored"],t0["flag"])
    if loc0: laid[loc0[0]].append(loc0[1])
for k0 in laid: laid[k0].sort()
orig_fs={k0:os.path.getsize(k0) for k0 in laid}
def gap_of(rdb,off):
    arr=laid[rdb]; j=bisect.bisect_right(arr,off)
    return (arr[j] if j<len(arr) else orig_fs[rdb])-off

files=[fn for fn in os.listdir("repack_in") if fn.endswith(".CHK") and fn not in ("COMMON_2D.CHK","COMMON_2D_ADD.CHK")]
targets=[]
for fn in files:
    o=os.path.join(RES,fn); k=os.path.join("repack_in",fn)
    if not os.path.isfile(o) or fn not in idxo: continue
    ob=open(o,'rb').read(); kb=open(k,'rb').read()
    if len(ob)==len(kb) and ob.find(b'NX  SUR ')<0 and ob!=kb:
        targets.append(fn)
tset=set(targets)
print(f"재주입 대상: {len(targets)}개")

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
per_file={}
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if not ko: continue
    jpb=s["jp"].encode("utf-8"); kob=ENC.encode(ko)
    for occ in s["occurrences"]:
        if occ["method"]=="scan" and occ["file"] in tset:
            per_file.setdefault(occ["file"],[]).append((jpb,kob))
for fn in per_file: per_file[fn]=list(dict.fromkeys(per_file[fn]))

def true_slot(fn):
    t=idxo[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,_=loc; key=R.file_key(fn)
    with open(rdb,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=bytearray(R.crypt(hraw,key)); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(rdb,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    body=zlib.decompress(d[32:32+clen]) if t["flag"]>0 else bytes(d[32:32+(t["DEC_SIZE"]-32)])
    return t,rdb,off,key,hdr,body

def strict_patch(buf, i, jplen, kob):
    """[i, i+jplen] 안에만 기록. 초과분 UTF-8경계 잘림. 반환=잘림여부."""
    nb=kob; tr=False
    if len(nb)>jplen:
        # ★버그수정: 연속바이트만 제거하면 리드바이트가 남아 댕글링(〓)+bleed-in.
        #   decode(ignore)로 불완전 마지막 문자 통째 제거 → 유효 UTF-8.
        nb=kob[:jplen].decode('utf-8','ignore').encode('utf-8')
        tr=True
    buf[i:i+len(nb)]=nb
    buf[i+len(nb):i+jplen]=b"\x00"*(jplen-len(nb))
    return tr

wf={}
def revert(fn):
    t=idxo[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,_=loc
    n=gap_of(rdb,off)
    with open(rdb,"rb") as f: f.seek(off); data=f.read(n)
    if rdb not in wf: wf[rdb]=open(os.path.join(OUT,rdb),"r+b")
    wf[rdb].seek(off); wf[rdb].write(data)

st=dict(files=0,hit=0,miss=0,trunc=0,nogap=0,ambig=0)
try:
    done=0
    for fn in targets:
        pairs=per_file.get(fn,[])
        if not pairs: revert(fn); st["miss"]+=1; continue
        t,rdb,off,key,hdr,body=true_slot(fn)
        buf=bytearray(body); changed=False
        for jpb,kob in pairs:
            jl=len(jpb); start=0; cnt=0; positions=[]
            while True:
                i=buf.find(jpb,start)
                if i<0: break
                pre = (i==0) or (buf[i-1]==0)
                post= (i+jl>=len(buf)) or (buf[i+jl]==0)
                if pre and post: positions.append(i)
                start=i+1
            for i in positions:
                if strict_patch(buf,i,jl,kob): st["trunc"]+=1
                st["hit"]+=1; changed=True
        if not changed: revert(fn); st["miss"]+=1; continue
        comp=zlib.compress(bytes(buf),9); need=R.align_up(32+len(comp),R.SECTOR)
        if need>gap_of(rdb,off): st["nogap"]+=1; revert(fn); continue
        struct.pack_into("<I",hdr,0x18,len(comp)); struct.pack_into("<I",hdr,0x1C,off//R.SECTOR)
        blob=bytearray(need); blob[:32]=hdr; blob[32:32+len(comp)]=comp
        enc=R.crypt(bytes(blob),key)
        if rdb not in wf: wf[rdb]=open(os.path.join(OUT,rdb),"r+b")
        wf[rdb].seek(off); wf[rdb].write(enc)
        st["files"]+=1; done+=1
        if done%100==0: print(f"  {done} 파일")
finally:
    for f in wf.values(): f.close()
print(f"\n완료: 파일 {st['files']}, 치환 {st['hit']}, 잘림 {st['trunc']}, 미매칭 {st['miss']}, 공간부족 {st['nogap']}")
print("안전모드: 문자열 밖 절대 미변경 + 양쪽NUL경계 매칭. RDI 불변.")
