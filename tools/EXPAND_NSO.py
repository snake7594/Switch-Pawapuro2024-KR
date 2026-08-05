# -*- coding: utf-8 -*-
"""NSO 세그먼트 재배치 확장: .rodata를 N(페이지배수) 늘리고 .data+bss를 뒤로 이동.
data/bss를 가리키는 모든 참조를 +N 갱신:
  - RELA 엔트리 r_offset / r_addend (data/bss 범위)
  - 코드(.text) ADRP 페이지 (data/bss 범위) → immhi/immlo 재인코딩
  - 코드 LDR-literal / ADR 타겟 (data/bss 범위)
새 영역 = 기존 .rodata 끝 ~ +N (VA 불변인 rodata 확장부). flags=0(무압축·무해시)이라 가능.
사용: python EXPAND_NSO.py <IN> <OUT> <N_hex>   (예: 0x100000)
검증: .text 재인코딩 외 코드 불변, 참조 일관성 assert."""
import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

IN = sys.argv[1] if len(sys.argv) > 1 else 'inject_out/main-new'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'inject_out/main-expand'
N = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x100000
assert N % 0x1000 == 0, "N은 페이지(0x1000) 배수"

b = bytearray(open(IN, 'rb').read())
def u32(o): return struct.unpack_from('<I', b, o)[0]
assert b[:4] == b'NSO0' and u32(0x0C) == 0, "NSO0 flags=0 아님"
TEXT_FO, TEXT_MO, TEXT_SZ = u32(0x10), u32(0x14), u32(0x18)
ROD_FO, ROD_MO, ROD_SZ = u32(0x20), u32(0x24), u32(0x28)
DATA_FO, DATA_MO, DATA_SZ = u32(0x30), u32(0x34), u32(0x38)
BSS = u32(0x3C)
DATA_MO_OLD = DATA_MO
BSS_END = DATA_MO + DATA_SZ + BSS
print(f"text MO={hex(TEXT_MO)} sz={hex(TEXT_SZ)} | rodata MO={hex(ROD_MO)} sz={hex(ROD_SZ)} | data MO={hex(DATA_MO)} sz={hex(DATA_SZ)} bss={hex(BSS)}")
print(f"확장 N={hex(N)}  data/bss 이동 → old_data_MO={hex(DATA_MO_OLD)} 이상 참조 +N")

RO_DELTA = ROD_MO - ROD_FO   # rodata fileoff→VA
def ro_fo2va(fo): return fo + RO_DELTA

# VA→파일 오프셋 (재배치 전 기준)
def va2fo(va):
    if TEXT_MO <= va < TEXT_MO + TEXT_SZ: return va - TEXT_MO + TEXT_FO
    if ROD_MO <= va < ROD_MO + ROD_SZ: return va - ROD_MO + ROD_FO
    if DATA_MO <= va < DATA_MO + DATA_SZ: return va - DATA_MO + DATA_FO
    return None

# ---- 동적섹션 파싱 ----
MOD0_FO = TEXT_FO + struct.unpack_from('<I', b, TEXT_FO+4)[0]
assert b[MOD0_FO:MOD0_FO+4] == b'MOD0'
MOD0_VA = (MOD0_FO - TEXT_FO) + TEXT_MO
dyn_off = struct.unpack_from('<i', b, MOD0_FO+4)[0]
DYN_VA = MOD0_VA + dyn_off
DYN_FO = va2fo(DYN_VA)
DYN = {}
o = DYN_FO
while True:
    tag, val = struct.unpack_from('<QQ', b, o)
    if tag == 0: break
    DYN.setdefault(tag, val); o += 16
JMPREL = DYN.get(23); PLTRELSZ = DYN.get(2, 0)
SYMTAB = DYN.get(6); SYMENT = DYN.get(11, 0x18); STRTAB = DYN.get(5)

def relo_update(tbl_va, sz):
    """RELA/JMPREL 테이블: r_offset/addend가 data/bss면 +N (위치 불변=rodata)."""
    fo = va2fo(tbl_va); cnt = sz // 24
    arr = np.frombuffer(bytes(b[fo:fo+cnt*24]), dtype='<u8').reshape(-1, 3).copy()
    ro, ri, ra = arr[:, 0], arr[:, 1], arr[:, 2]
    mo = ro >= DATA_MO_OLD; ma = (ra >= DATA_MO_OLD) & (ra < BSS_END)
    ro[mo] += N; ra[ma] += N
    b[fo:fo+cnt*24] = np.stack([ro, ri, ra], axis=1).astype('<u8').tobytes()
    return int(mo.sum()), int(ma.sum())

# ---- 1) RELA + JMPREL 갱신 ----
r1 = relo_update(DYN[7], DYN[8])
print(f"RELA 갱신: r_offset {r1[0]} + addend {r1[1]}")
if JMPREL:
    r2 = relo_update(JMPREL, PLTRELSZ)
    print(f"JMPREL 갱신: r_offset {r2[0]} + addend {r2[1]} ({PLTRELSZ//24}엔트리)")

# ---- 2) SYMTAB st_value 갱신 (data/bss 가리키는 심볼) ----
if SYMTAB and STRTAB:
    sfo = va2fo(SYMTAB); nsym = (STRTAB - SYMTAB) // SYMENT
    cs = 0
    for i in range(nsym):
        vpos = sfo + i*SYMENT + 8   # st_value 오프셋
        sv = struct.unpack_from('<Q', b, vpos)[0]
        if DATA_MO_OLD <= sv < BSS_END:
            struct.pack_into('<Q', b, vpos, sv + N); cs += 1
    print(f"SYMTAB st_value 갱신: {cs}/{nsym}")

# ---- 3) .dynamic 값 갱신 (data/bss 가리키는 DT_) ----
o = DYN_FO; cd = 0
while True:
    tag, val = struct.unpack_from('<QQ', b, o)
    if tag == 0: break
    if tag not in (2, 8, 10, 11, 27, 28, 9, 20, 0x6ffffff9) and DATA_MO_OLD <= val < BSS_END:
        struct.pack_into('<Q', b, o+8, val + N); cd += 1
    o += 16
print(f".dynamic 주소값 갱신: {cd}")

# ---- 4) MOD0 필드 전체 갱신 (dynamic/bss_start/bss_end/module_object 등 data·bss 가리키면 +N) ----
MOD0_NAMES = {1: 'dynamic', 2: 'bss_start', 3: 'bss_end', 4: 'ehframe_s', 5: 'ehframe_e', 6: 'module_object'}
cm = []
for i in range(1, 7):
    off = struct.unpack_from('<i', b, MOD0_FO+i*4)[0]
    va = MOD0_VA + off
    if DATA_MO_OLD <= va <= BSS_END:
        struct.pack_into('<i', b, MOD0_FO+i*4, off + N)
        cm.append(MOD0_NAMES[i])
print(f"MOD0 필드 +N: {cm}")

# ---- 2) 코드 ADRP/ADR/LDR-literal 갱신 (data/bss 페이지 참조) ----
text = np.frombuffer(bytes(b[TEXT_FO:TEXT_FO+TEXT_SZ]), dtype='<u4').copy()
pc = TEXT_MO + np.arange(len(text), dtype=np.int64) * 4
w = text.astype(np.int64)
# ADRP: (w&0x9f000000)==0x90000000
adrp = (text & 0x9f000000) == 0x90000000
ai = np.nonzero(adrp)[0]
wi = w[ai]; immlo = (wi >> 29) & 3; immhi = (wi >> 5) & 0x7ffff
imm = (immhi << 2) | immlo; imm = np.where(imm & (1 << 20), imm - (1 << 21), imm)
page = (pc[ai] & ~0xfff) + imm * 0x1000
sel = page >= DATA_MO_OLD              # data/bss 페이지
npg = page.copy(); npg[sel] += N
# 재인코딩
newpageimm = ((npg - (pc[ai] & ~0xfff)) // 0x1000)
ni_lo = (newpageimm & 3); ni_hi = (newpageimm >> 2) & 0x7ffff
neww = (text[ai].astype(np.uint32) & ~np.uint32(0x60ffffe0)) | (ni_lo.astype(np.uint32) << 29) | (ni_hi.astype(np.uint32) << 5)
text[ai[sel]] = neww[sel]
print(f"ADRP 갱신: {int(sel.sum())}/{len(ai)}")
# ADR: (w&0x9f000000)==0x10000000 (PC상대 ±1MB, 절대주소)
adr = (text & 0x9f000000) == 0x10000000
di = np.nonzero(adr)[0]
wd = w[di]; dlo = (wd >> 29) & 3; dhi = (wd >> 5) & 0x7ffff
dimm = (dhi << 2) | dlo; dimm = np.where(dimm & (1 << 20), dimm - (1 << 21), dimm)
dtgt = pc[di] + dimm
dsel = dtgt >= DATA_MO_OLD
assert not dsel.any(), f"ADR가 data 참조({int(dsel.sum())}개) — ±1MB 초과 재배치 불가, 별도 처리 필요"
# LDR literal: (w&0x3b000000)==0x18000000, 타겟=pc+imm19*4
ldr = (text & 0x3b000000) == 0x18000000
li = np.nonzero(ldr)[0]
wl = w[li]; imm19 = (wl >> 5) & 0x7ffff; imm19 = np.where(imm19 & (1 << 18), imm19 - (1 << 19), imm19)
ltgt = pc[li] + imm19 * 4
lsel = ltgt >= DATA_MO_OLD
assert not lsel.any(), f"LDR-literal이 data 참조({int(lsel.sum())}개) — 별도 처리 필요"
b[TEXT_FO:TEXT_FO+TEXT_SZ] = text.tobytes()

# ---- 3) 헤더 갱신 ----
struct.pack_into('<I', b, 0x28, ROD_SZ + N)     # rodata Dsize
struct.pack_into('<I', b, 0x64, u32(0x64) + N)  # rodata filesize
struct.pack_into('<I', b, 0x30, DATA_FO + N)    # data FileOff
struct.pack_into('<I', b, 0x34, DATA_MO + N)    # data MemOff
# bss_size, data Dsize/filesize 불변

# ---- 4) 파일 재구성: [text+rodata][N바이트 0][data] ----
out = bytearray()
out += b[:DATA_FO]              # text + rodata (원본)
out += bytes(N)                 # 새 영역(0)
out += b[DATA_FO:]              # data (뒤로 밀림)
# 헤더는 b(수정본)의 앞부분 사용됨(out[:DATA_FO]=b[:DATA_FO], 헤더 포함)
open(OUT, 'wb').write(bytes(out))
new_area_fo = DATA_FO           # 새 영역 파일오프셋 시작
new_area_va = ro_fo2va(DATA_FO) # = ROD_MO + (DATA_FO-ROD_FO); rodata 확장부 VA
print(f"→ {OUT}  크기 {len(out)} (+{hex(N)})")
print(f"새 영역: fileoff {hex(new_area_fo)}~+{hex(N)}, VA {hex(new_area_va)}~ (rodata 확장부)")
import hashlib
print(f"md5 {hashlib.md5(bytes(out)).hexdigest()}")
