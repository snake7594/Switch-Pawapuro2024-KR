# -*- coding: utf-8 -*-
"""진짜 redirect 안전성 검증 — exe_inject 로직 재현 후 각 redirect 대상 검사:
   1) 손댄 포인터 위치가 실제 원본에서 '해당 문자열 VA'를 가리켰는가 (오탐 포인터 아님)
   2) 새 VA가 .rodata 풀 안이고, 거기 한글(한자코드) 문자열 + NUL이 실제로 있는가
   3) 잘림 1141건이 어떤 문자열인지(중요 UI면 위험) 요약"""
import sys, struct, os, json
from collections import defaultdict
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용
import inject_all as IA

SRC="!exefs-작업/main-원본"; NEW="inject_out/main"
data=bytearray(open(SRC,'rb').read())
bn=bytearray(open(NEW,'rb').read())
tx_fo,tx_mo,tx_sz=struct.unpack_from('<III',data,0x10)
ro_fo,ro_mo,ro_sz=struct.unpack_from('<III',data,0x20)
da_fo,da_mo,da_sz=struct.unpack_from('<III',data,0x30)
lo,hi=ro_mo,ro_mo+ro_sz

# pidx (원본 기준)
pidx=defaultdict(list)
for seg_fo,seg_sz in [(ro_fo,ro_sz),(da_fo,da_sz)]:
    for shift in (0,4):
        base=seg_fo+shift; n=(seg_sz-shift)//8
        arr=np.frombuffer(bytes(data[base:base+n*8]),dtype='<u8')
        mask=(arr>=lo)&(arr<hi)
        for i in np.nonzero(mask)[0]:
            pidx[int(arr[i])].append(base+int(i)*8)

doc=json.load(open("번역_일본어.json",encoding='utf-8'))
jobs=[]
for s in doc["strings"]:
    ko=s.get("ko","").strip()
    if not ko: continue
    kob=IA.ENC_EXE.encode(ko)
    for o in s["occurrences"]:
        if o["method"]=="exe":
            jobs.append((o["offset"],o["len"],kob,s["jp"],ko))

# redirect 후보 재현: 제자리 안 되는 것 중 pidx 있는 것
redir=[]; trunc_list=[]
for off,old_len,kob,jp,ko in jobs:
    T=0;k=off+old_len
    while k<len(data) and data[k]==0: T+=1;k+=1
    cap=old_len+T-1 if T>0 else old_len
    if len(kob)<=cap: continue
    va=ro_mo+(off-ro_fo)
    if pidx.get(va): redir.append((off,va,kob,jp,ko))
    else: trunc_list.append((off,old_len,kob,jp,ko))

print(f"redirect 대상 {len(redir)}, 잘림(포인터없음) {len(trunc_list)}")

# 검증 1&2: 신본에서 그 포인터들이 .rodata 안 새 VA를 가리키고, 거기 문자열이 있는가
bad_ptr=0; bad_str=0; ok=0
sample=[]
for off,va,kob,jp,ko in redir:
    locs=pidx[va]
    # 신본에서 첫 포인터 위치의 값
    nv=struct.unpack_from('<Q',bn,locs[0])[0]
    if not (lo<=nv<hi): bad_ptr+=1; continue
    nfo=ro_fo+(nv-ro_mo)
    got=bytes(bn[nfo:nfo+len(kob)])
    term = nfo+len(kob)<len(bn) and bn[nfo+len(kob)]==0
    if got==kob and term: ok+=1
    else: bad_str+=1
    if len(sample)<5: sample.append((jp,ko,va,nv,got==kob))
print(f"  redirect 검증: 정상 {ok}, 포인터범위밖 {bad_ptr}, 문자열불일치 {bad_str}")
for jp,ko,va,nv,m in sample:
    print(f"    {jp[:16]!r}->{ko[:16]!r} va0x{va:x}→0x{nv:x} 문자열OK={m}")

# 검증 3: 잘림 목록 요약 (한글 길이 vs 원본, 심한 잘림)
print(f"\n잘림 {len(trunc_list)}건 중 심한 것(한글 절반이상 손실) 상위:")
sev=[]
for off,old_len,kob,jp,ko in trunc_list:
    T=0;k=off+old_len
    while k<len(data) and data[k]==0:T+=1;k+=1
    cap=old_len+T-1 if T>0 else old_len
    loss=len(kob)-cap
    if loss>0: sev.append((loss,jp,ko,cap,len(kob)))
sev.sort(reverse=True)
for loss,jp,ko,cap,klen in sev[:15]:
    print(f"    -{loss}B  jp={jp[:20]!r} ko={ko[:20]!r} (cap={cap},koB={klen})")
print(f"  실제 손실 발생 잘림: {len(sev)}건 / 전체 잘림 {len(trunc_list)}")
