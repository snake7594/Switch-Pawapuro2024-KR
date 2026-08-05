# -*- coding: utf-8 -*-
"""신주입본 exe 안전성 검증:
 A) 변경이 .rodata 한정인지 (이미 확인: text/data/헤더 0)
 B) redirect로 바뀐 8B 포인터들이 모두 .rodata 범위 VA를 가리키는지 (out-of-range 크래시 방지)
 C) 재주입 문자열이 실제로 원래 위치 근처(제자리)거나 zero-run 풀 안인지
 D) '한글 인코딩(한자코드)'이 실제로 반영됐는지 (원문→한자 치환 샘플)
 E) redirect가 손댄 포인터가 문자열테이블이 아닌 코드/구조 포인터일 위험 점검"""
import sys, struct, os, json
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용

SRC="!exefs-작업/main-원본"; NEW="inject_out/main"
bo=bytearray(open(SRC,'rb').read()); bn=bytearray(open(NEW,'rb').read())
tx_fo,tx_mo,tx_sz=struct.unpack_from('<III',bo,0x10)
ro_fo,ro_mo,ro_sz=struct.unpack_from('<III',bo,0x20)
da_fo,da_mo,da_sz=struct.unpack_from('<III',bo,0x30)
print(f".rodata: file[0x{ro_fo:x},0x{ro_fo+ro_sz:x}) VA[0x{ro_mo:x},0x{ro_mo+ro_sz:x})")

# B) 8B 포인터 변경 검사 (전 구간)
ao=np.frombuffer(bytes(bo),dtype=np.uint8); an=np.frombuffer(bytes(bn),dtype=np.uint8)
diff=np.nonzero(ao!=an)[0]
print(f"총 변경 {len(diff):,}바이트, 범위 [0x{diff.min():x},0x{diff.max():x}]")

# 변경 위치를 8바이트 단위로 그룹핑해서 '포인터 교체'로 보이는 것 추출
# ro/da에서 8B정렬 워드 중 값이 바뀐 것 = redirect 후보
def changed_ptrs(seg_fo, seg_sz, seg_name):
    res=[]
    for shift in (0,4):
        base=seg_fo+shift; n=(seg_sz-shift)//8
        o=np.frombuffer(bytes(bo[base:base+n*8]),dtype='<u8')
        w=np.frombuffer(bytes(bn[base:base+n*8]),dtype='<u8')
        ch=np.nonzero(o!=w)[0]
        for i in ch:
            res.append((base+int(i)*8, int(o[i]), int(w[i])))
    return res
ptr_ch = changed_ptrs(ro_fo,ro_sz,'ro') + changed_ptrs(da_fo,da_sz,'da')
print(f"\n8B정렬 워드 변경(포인터 redirect 후보): {len(ptr_ch)}개")
# 이 중 '원래 VA→새 VA'로 둘 다 .rodata 안인 것 = 정상 redirect
lo,hi=ro_mo,ro_mo+ro_sz
good=bad_old=bad_new=0
bad_examples=[]
for loc,ov,nv in ptr_ch:
    old_in = lo<=ov<hi; new_in = lo<=nv<hi
    if old_in and new_in: good+=1
    else:
        if not new_in: bad_new+=1;
        if not old_in: bad_old+=1
        if len(bad_examples)<10: bad_examples.append((loc,ov,nv,old_in,new_in))
print(f"  정상(old·new 둘다 .rodata): {good}")
print(f"  new_va가 .rodata밖(위험!): {bad_new}   old_va가 .rodata밖: {bad_old}")
for loc,ov,nv,oi,ni in bad_examples:
    print(f"    @file0x{loc:x}: 0x{ov:x}(in={oi}) -> 0x{nv:x}(in={ni})")

# 하지만 대부분 변경은 '문자열 바이트 직접 치환'이라 8B정렬 아님. 포인터 후보가 과다검출됨.
# 진짜 redirect만 세려면: 변경워드가 '유효 VA→유효 VA'이고 old_va 위치에 원래 문자열 시작이 있었는지.
print("\n주의: 위 카운트는 문자열 바이트가 우연히 8B워드로 잡힌 오검출 포함. 실제 redirect는 exe_inject 로그의 redirect 수 참조.")

# D) 한자코드 반영 샘플: exe occurrence 몇 개를 원본/신본 비교
doc=json.load(open("번역_일본어.json",encoding='utf-8'))
import inject_all as IA
shown=0
for s in doc["strings"]:
    ko=str(s.get("ko","")).strip()
    if not ko: continue
    for o in s["occurrences"]:
        if o["method"]=="exe" and shown<8:
            off=o["offset"]; ln=o["len"]
            orig=bytes(bo[off:off+ln])
            new=bytes(bn[off:off+ln])
            try: os_=orig.decode('utf-8','replace')
            except: os_=str(orig)
            print(f"\n  [{o['file']}] off=0x{off:x} len={ln}")
            print(f"    jp: {s['jp'][:30]!r}")
            print(f"    ko: {ko[:30]!r}")
            print(f"    원본바이트: {orig[:24].hex()}")
            print(f"    신본바이트: {new[:24].hex()}  {'(변경됨)' if orig!=new else '(동일!)'}")
            shown+=1
    if shown>=8: break
