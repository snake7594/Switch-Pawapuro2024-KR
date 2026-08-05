# -*- coding: utf-8 -*-
"""SEN_* 선수 로스터 CHK의 선수명 슬랙 전체복구(잘림 해결).
   SEN_MAIN 등은 이름 필드가 고정폭(예 84B: 이름+0패딩). REINJECT strict_patch는 슬랙 미사용→읽기 긴 성씨 잘림.
   여기선 진짜베이스(root RDB) body에서 사전(jp→ko) 일본어명을 NUL경계 탐색→patch_at_offset(슬랙 사용, clean).
   한글은 짧아 필드 내에만 기록되고, 뒤 0런은 NUL패딩(0→0 무해)이라 스탯/구조 안 건드림. body 크기 불변.
   재압축 gap 적합 시 repack_out 제자리 기록(재배치 회피), RDI decsize 갱신. gap부족은 스킵(현 잘림 유지).
   대상: SEN_* 로스터(SEN_TEXT* 제외)."""
import os, sys, struct, zlib, json, bisect, re
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT); sys.path.insert(0,ROOT)
import REPACK_AUTO as R, inject_lib as L
ENC=L.Encoder(os.path.join("!exefs-작업","hangul_to_hanja.tsv"))  # 통일: tsv — 2026-07-03 폰트 단일화
OUT="repack_out"
ctrl_re=re.compile('[\x00-\x08\x0b-\x1f]')
seg_re=re.compile(rb'(?<=\x00)([^\x00]{2,80})(?=\x00)')

dec,tab,idx,rec=R.load_rdi(os.path.join(OUT,"RES00.RDI"))
laid={"RES00.RDB":[], "RES10.RDB":[]}
for t in tab:
    loc=R.locate(t["stored"],t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
osz={k:os.path.getsize(k) for k in laid}
def gap_of(rdb,off):
    a=laid[rdb]; j=bisect.bisect_right(a,off)
    return (a[j] if j<len(a) else osz[rdb])-off

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
jpko={}
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if ko and ko!=s["jp"] and not ctrl_re.search(s["jp"]) and len(s["jp"])>=1:
        jpko[s["jp"]]=ENC.encode(ko)

targets=[fn for fn in idx if fn.startswith("SEN_") and not fn.startswith("SEN_TEXT")]
print(f"대상 SEN_* 로스터: {len(targets)}개")

def read_true(fn):
    t=idx[fn]; loc=R.locate(t["stored"],t["flag"]); rdb,off,is10=loc; key=R.file_key(fn)
    with open(rdb,"rb") as f: f.seek(off); hraw=f.read(32)
    hdr=bytearray(R.crypt(hraw,key)); clen=struct.unpack_from("<I",hdr,0x18)[0]
    with open(rdb,"rb") as f: f.seek(off); raw=f.read(R.align_up(32+clen,4))
    if len(raw)%4: raw+=b"\x00"*(4-len(raw)%4)
    d=R.crypt(raw,key)
    body=zlib.decompress(d[32:32+clen]) if t["flag"]>0 else bytes(d[32:32+(t["DEC_SIZE"]-32)])
    return t,rdb,off,key,hdr,body

fh={}; st=dict(files=0,names=0,nogap=0,full=0,trunc=0)
try:
  for fn in sorted(targets):
    t,rdb,off,key,hdr,body=read_true(fn)
    if body.find(b"NX  SUR ")>=0: continue  # 이미지 아님(로스터는 BIN)
    buf=bytearray(body); matched=[]
    for m in seg_re.finditer(bytes(body)):
        try: s=m.group(1).decode("utf-8")
        except: continue
        if s in jpko: matched.append((m.start(1), len(m.group(1)), jpko[s]))
    if not matched: continue
    hits=0
    for pos,jl,kob in matched:
        tr=L.patch_at_offset(buf,pos,jl,kob)
        st["trunc" if tr else "full"]+=1; hits+=1
    assert len(buf)==len(body)
    if t["flag"]>0: comp=zlib.compress(bytes(buf),9); nd=R.align_up(len(buf),4)
    else: comp=bytes(buf); nd=R.align_up(32+len(buf),4)
    need=R.align_up(32+len(comp),4); g=gap_of(rdb,off)
    if need>g: st["nogap"]+=1; print(f"  [gap부족 스킵] {fn} {need}>{g}"); continue
    struct.pack_into("<I",hdr,0x18,len(comp) if t["flag"]>0 else nd)
    struct.pack_into("<I",hdr,0x1C,off//R.SECTOR)
    blob=bytearray(need); blob[:32]=hdr; blob[32:32+len(comp)]=comp
    enc=R.crypt(bytes(blob),key)
    if rdb not in fh: fh[rdb]=open(os.path.join(OUT,rdb),"r+b")
    fh[rdb].seek(off); fh[rdb].write(enc)
    struct.pack_into("<I",dec,rec+t["i"]*9+4,nd)
    st["files"]+=1; st["names"]+=hits
    print(f"  [OK] {fn}: 선수명 {hits}건(완전{sum(1 for p,j,k in matched)}) comp{len(comp)}")
finally:
    for f in fh.values(): f.close()
R.save_rdi(dec, os.path.join(OUT,"RES00.RDI"))
print(f"\n완료: 파일 {st['files']}, 이름치환 {st['names']} (완전복구 {st['full']}, 슬랙후잘림 {st['trunc']}), gap부족 {st['nogap']}")
print("폰트=wReplace/메인. body크기불변·NUL패딩무해=구조안전.")
