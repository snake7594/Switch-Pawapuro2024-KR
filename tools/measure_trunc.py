# -*- coding: utf-8 -*-
"""슬랙 인식 후에도 초과하는 항목을 방식별로 측정 + exe 초과의 포인터 재배치 가능성."""
import json, struct
import numpy as np
import inject_all as IA
import inject_lib as L

doc = json.load(open("번역_일본어.json", encoding="utf-8"))
b = open("!exefs-작업/main-원본", "rb").read()
ro_fo, ro_mo, ro_sz = struct.unpack_from("<III", b, 0x20)
da_fo, da_mo, da_sz = struct.unpack_from("<III", b, 0x30)

def slack(buf, off, ln):
    T = 0; k = off + ln
    while k < len(buf) and buf[k] == 0: T += 1; k += 1
    return T

# exe: main 한 번 로드, 초과 + 포인터유무
def collect_ptrset():
    def cc(fo, sz):
        arr = np.frombuffer(b[fo:fo+sz-(sz % 8)], dtype="<u8")
        lo, hi = ro_mo, ro_mo+ro_sz
        s = set(int(v) for v in arr[(arr >= lo) & (arr < hi)])
        arr2 = np.frombuffer(b[fo+4:fo+4+(sz-4)-((sz-4) % 8)], dtype="<u8")
        s |= set(int(v) for v in arr2[(arr2 >= lo) & (arr2 < hi)])
        return s
    return cc(ro_fo, ro_sz) | cc(da_fo, da_sz)
ptrset = collect_ptrset()

exe_over = 0; exe_over_ptr = 0; exe_fit = 0
scan_over = 0; scan_fit = 0
# scan: 파일별 캐시
import os
cache = {}
def get(fn):
    if fn not in cache:
        p = os.path.join("RES_추출원본", fn)
        cache[fn] = open(p, "rb").read() if os.path.isfile(p) else b""
    return cache[fn]

for s in doc["strings"]:
    ko = s.get("ko", "").strip()
    if not ko: continue
    for o in s["occurrences"]:
        m = o["method"]
        if m == "string": continue
        enc = IA.ENC_EXE if m == "exe" else IA.ENC_CHK
        kob = enc.encode(ko)
        if m == "exe":
            T = slack(b, o["offset"], o["len"])
            if len(kob) <= o["len"]+T-1: exe_fit += 1
            else:
                exe_over += 1
                va = ro_mo + (o["offset"]-ro_fo)
                if va in ptrset: exe_over_ptr += 1
        else:
            src = get(o["file"])
            if not src: continue
            T = slack(src, o["offset"], o["len"])
            if len(kob) <= o["len"]+T-1: scan_fit += 1
            else: scan_over += 1

print("=== 슬랙 인식 후 초과(잘림) 분석 ===")
print("exe:  맞음 %d, 초과 %d  → 초과 중 포인터재배치가능 %d (%.0f%%), pcrel(명령패치필요) %d"
      % (exe_fit, exe_over, exe_over_ptr, 100*exe_over_ptr/max(exe_over, 1), exe_over-exe_over_ptr))
print("scan: 맞음 %d, 초과 %d" % (scan_fit, scan_over))
print("→ exe 초과의 %.0f%%는 포인터 redirect로 해결 가능(.rodata 풀 3.36MB)" % (100*exe_over_ptr/max(exe_over,1)))
