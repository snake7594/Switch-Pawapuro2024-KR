# -*- coding: utf-8 -*-
"""UNCDFONT 청크 2개의 위치/헤더 덤프 + FONT1(0xD9540)/FONT2(0x64F638) 지점 확인."""
import os, sys, struct
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.environ.get("PAWA_ROOT", os.getcwd()); os.chdir(ROOT)
def u32(b,o): return struct.unpack_from("<I",b,o)[0]
def u16(b,o): return struct.unpack_from("<H",b,o)[0]

o=open("COMMON_2D-o.CHK",'rb').read()
CHK=32
di=u32(o,CHK+16); ds=u32(o,CHK+20)
pos=CHK+di; hi=CHK+ds
uncd=[]
while pos<hi:
    ts=u32(o,pos+8); ct=o[pos+16:pos+24]
    if ts==0 or pos+ts>len(o): break
    if ct==b"UNCDFONT": uncd.append((pos,ts))
    pos+=ts
print("UNCDFONT 청크:")
for p,ts in uncd:
    print(f"  @0x{p:x}  ts={ts} (0x{ts:x})  끝=0x{p+ts:x}")

# 폴더 메모 오프셋 확인 (파일 절대? 청크 상대?)
for tag,off in (("FONT1",0xD9540),("FONT2",0x64F638)):
    print(f"\n{tag} 오프셋 0x{off:x}:")
    print(f"  파일절대 기준 바이트: {o[off:off+32].hex()}")
    for p,ts in uncd:
        if 0<=off-p<ts:
            print(f"  → UNCDFONT@0x{p:x} 내부 상대 0x{off-p:x}")

# 각 UNCDFONT 헤더 덤프 (앞 0x120)
for p,ts in uncd:
    print(f"\n===== UNCDFONT @0x{p:x} 헤더 =====")
    for r in range(0,0x120,16):
        row=o[p+r:p+r+16]
        hexs=' '.join(f'{b:02x}' for b in row)
        asc=''.join(chr(b) if 32<=b<127 else '.' for b in row)
        print(f"  +{r:04x}: {hexs}  {asc}")
    # u32 해석 (0x18~0x60)
    print("  u32 필드:")
    for r in range(0x18,0x68,4):
        v=u32(o,p+r)
        note=""
        if 0<v<ts: note=f" (청크내 오프셋? → 절대 0x{p+v:x})"
        print(f"    +0x{r:02x}: {v} (0x{v:x}){note}")
