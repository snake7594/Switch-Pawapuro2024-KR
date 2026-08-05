# -*- coding: utf-8 -*-
"""안전 exe(main) 한글주입 — 크래시 방지 최우선.
   원칙(사용자 검증 2-1u.py 방식):
     - 제자리 치환만. 원본 문자열 바이트 범위 [off, off+len] 안에만 기록.
     - 한글이 짧으면 0x00 패딩(원본 종료NUL 유지).
     - 한글이 길면 UTF-8 경계로 '잘라서' 범위 내에만(구조 절대 미침범).
     - 포인터 redirect 없음, NSO 재빌드 없음 → 파일크기·.text·.data·헤더 전부 불변.
   → 구조/포인터/점프테이블 손상 원천 차단 (garbage 코드점프 크래시 방지).
   인코딩: hangul_to_hanja.tsv (exe=ADD 폰트블록, 가→亜). 폰트B의 COMMON_2D_ADD가 렌더.
   출력: inject_out/main-safe"""
import os, sys, struct, json
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용; sys.path.insert(0,".")
import inject_lib as L

SRC="!exefs-작업/main-원본"; OUT="inject_out/main-safe"
ENC=L.Encoder(os.path.join("!exefs-작업","hangul_to_hanja.tsv"))

data=bytearray(open(SRC,"rb").read())
orig=bytes(data)
tx_fo,tx_mo,tx_sz=struct.unpack_from("<III",data,0x10)
ro_fo,ro_mo,ro_sz=struct.unpack_from("<III",data,0x20)
da_fo,da_mo,da_sz=struct.unpack_from("<III",data,0x30)
ro_end=ro_fo+ro_sz

doc=json.load(open("번역_일본어.json",encoding="utf-8"))
jobs=[]
for s in doc["strings"]:
    ko=s.get("ko","").strip()
    if not ko: continue
    kob=ENC.encode(ko)
    for o in s["occurrences"]:
        if o["method"]=="exe":
            jobs.append((o["offset"], o["len"], kob, s["jp"]))
print(f"exe 번역 occurrence: {len(jobs)}")

st=dict(fit=0, pad=0, trunc=0, skip_range=0, empty=0)
for off,ln,kob,jp in jobs:
    if off<ro_fo or off+ln>ro_end:   # .rodata 밖이면 절대 안 건드림
        st["skip_range"]+=1; continue
    nb=kob
    if len(nb)>ln:                    # 길면 UTF-8 경계로 잘라 범위 내에만
        # ★버그수정: 단순 연속바이트 제거는 리드바이트를 남겨 댕글링(〓)+bleed-in 유발.
        #   decode(ignore)로 불완전 마지막 문자를 통째 제거 → 유효 UTF-8 보장.
        nb=kob[:ln].decode('utf-8','ignore').encode('utf-8')
        st["trunc"]+=1
    elif len(nb)==ln: st["fit"]+=1
    else: st["pad"]+=1
    if not nb: st["empty"]+=1; continue
    data[off:off+len(nb)]=nb
    data[off+len(nb):off+ln]=b"\x00"*(ln-len(nb))   # 나머지 0x00, 종료NUL(off+ln)은 불변

# 안전성 자가검증: 변경이 .rodata 안에만 있는지
import numpy as np
ao=np.frombuffer(orig,dtype=np.uint8); an=np.frombuffer(bytes(data),dtype=np.uint8)
diff=np.nonzero(ao!=an)[0]
in_ro=((diff>=ro_fo)&(diff<ro_end)).sum()
in_tx=((diff>=tx_fo)&(diff<tx_fo+tx_sz)).sum()
in_da=((diff>=da_fo)&(diff<da_fo+da_sz)).sum()
in_hdr=(diff<0x100).sum()
print(f"\n변경 {len(diff):,}바이트: .rodata={in_ro:,} .text={in_tx} .data={in_da} 헤더={in_hdr}")
assert in_tx==0 and in_da==0 and in_hdr==0, "⚠️ .rodata 밖 변경 발생!"
assert len(data)==len(orig), "크기 변동!"

os.makedirs("inject_out", exist_ok=True)
open(OUT,"wb").write(data)
print(f"통계: 딱맞음 {st['fit']}, 패딩(짧음) {st['pad']}, 잘림(김) {st['trunc']}, 범위밖스킵 {st['skip_range']}, 빈값 {st['empty']}")
print(f"✅ 안전빌드: .text/.data/헤더 0변경, 크기불변, redirect·재빌드 없음 → {OUT}")
