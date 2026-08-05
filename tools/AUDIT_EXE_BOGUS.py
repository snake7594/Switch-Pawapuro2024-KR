# -*- coding: utf-8 -*-
"""exe(main-safe22) 바이너리 오탐 주입 감사 → main-safe23.
- 대상: strings 영역(> DYN_END)의 diff만. DYNAMIC[0x2aafb79,0x3d2551d]·pre-rodata 불변 assert.
- 죽은풀 기록(원본 run 시작 바이트==0) = 의도적(redirect 타깃) → 유지.
- 원본 세그먼트가 plausible_jp 실패(제어문자/허용문자밖/가나0&희귀한자) → 원본복원."""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np
from _plaus import plausible_jp

ob = open('main', 'rb').read()
buf = bytearray(open('inject_out/main-safe22', 'rb').read())
assert len(ob) == len(buf)
DYN = (0x2aafb79, 0x3d2551d)
a = np.frombuffer(bytes(buf), dtype=np.uint8); b = np.frombuffer(ob, dtype=np.uint8)
diff = np.nonzero(a != b)[0]
pre = int((diff < DYN[0]).sum() - ((diff >= 0x2aafb21) & (diff < DYN[0])).sum())
dyn = int(((diff >= DYN[0]) & (diff < DYN[1])).sum())
print(f"diff 총 {len(diff)}; pre-rodata {pre}, DYN {dyn} (불변 유지)")

runs = []
sel = diff[diff >= DYN[1]]
s0 = p = int(sel[0])
for x in sel[1:]:
    x = int(x)
    if x <= p + 1: p = x; continue
    runs.append((s0, p)); s0 = p = x
runs.append((s0, p))
print(f"strings 영역 diff run {len(runs)}")

stats = dict(pool=0, kept=0, restored=0)
handled = set(); samples = []
for (rs, re_) in runs:
    if ob[rs] == 0:      # 죽은풀 기록 = redirect 타깃, 유지
        stats['pool'] += 1; continue
    st = rs
    while st > DYN[1] and ob[st-1] != 0: st -= 1
    if st in handled: continue
    handled.add(st)
    oe = ob.find(b'\x00', st)
    if oe < 0: oe = len(ob)
    try: ojp = ob[st:oe].decode('utf-8')
    except UnicodeDecodeError: ojp = None
    T = 0; k = oe
    while k < len(ob) and ob[k] == 0: T += 1; k += 1
    region_end = oe + T
    if ojp is None or not plausible_jp(ojp, lenient=True):
        buf[st:region_end] = ob[st:region_end]
        stats['restored'] += 1
        if len(samples) < 12 and ojp: samples.append(ojp[:40])
    else:
        stats['kept'] += 1
open('inject_out/main-safe23', 'wb').write(bytes(buf))
print(f"완료: {stats}")
print("복원 표본:", *[repr(s) for s in samples], sep='\n  ')
# 사후 assert: DYN·pre-rodata가 safe22와 동일
c = np.frombuffer(bytes(buf), dtype=np.uint8)
assert (c[:DYN[1]] == a[:DYN[1]]).all(), "금지영역 변경 발생!"
print("금지영역 불변 확인 OK → inject_out/main-safe23")
