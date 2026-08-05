# -*- coding: utf-8 -*-
"""대사 조각 주변 raw 바이트 덤프 (원본 vs 안전패치) — 제어코드/조립구조/〓 규명."""
import sys, struct
sys.stdout.reconfigure(encoding='utf-8')
import os
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용

o=open("!exefs-작업/main-원본","rb").read()
n=open("inject_out/main-safe","rb").read()

def show(off, span=0xC0, label=""):
    print(f"\n===== @0x{off:x} {label} =====")
    lo=off-0x20; hi=off+span
    for base,tag in ((o,"원본"),(n,"패치")):
        seg=base[lo:hi]
        # 라인별
        print(f"  --{tag}--")
        for r in range(0,len(seg),24):
            chunk=seg[r:r+24]
            hx=' '.join(f'{b:02x}' for b in chunk)
            # 텍스트(제어코드는 ·, 0x00은 ▯)
            asc=''
            for b in chunk:
                if b==0: asc+='▯'
                elif b<0x20 or b==0x7f: asc+='◆'  # 제어코드 강조
                elif 0x20<=b<0x7f: asc+=chr(b)
                else: asc+='.'
            print(f"    +{lo+r-off:+05x}: {hx}  {asc}")

# 스크린샷3 대사
show(0x3db74a6, 0x100, "、きみがスーパースターとして (스샷3)")
