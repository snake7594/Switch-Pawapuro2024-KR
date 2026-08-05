# -*- coding: utf-8 -*-
"""main-safe15 → main-safe17: 부팅 크리티컬 동적구조 침범만 정확 수리.
크리티컬 영역 = [JMPREL, STRTAB끝] = 파일 [0x3d0e8e9, 0x3d2551d] (RELA는 부팅안전이라 보존).
방법(포인터-우선, 견고):
  1) safe15의 모든 8B 포인터 중 값이 크리티컬 VA범위이고 원본과 다른 것(=내가 심은 것) 수집
  2) 그 타깃 문자열을 크리티컬 밖 죽은풀로 이주 + 포인터 갱신(공유 문자열 dedup)
  3) 크리티컬 영역 바이트를 원본으로 복원
검증: 크리티컬==원본(0 diff), 크리티컬 가리키는 '변경된' 포인터 0, .text/헤더 불변."""
import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

orig = open(r'!exefs-작업/main-원본', 'rb').read()
data = bytearray(open('inject_out/main-safe15', 'rb').read())
tx_fo, tx_mo, tx_sz = struct.unpack_from('<III', orig, 0x10)
ro_fo, ro_mo, ro_sz = struct.unpack_from('<III', orig, 0x20)
da_fo, da_mo, da_sz = struct.unpack_from('<III', orig, 0x30)
ro_lo, ro_hi = ro_mo, ro_mo + ro_sz
def off_of(va): return ro_fo + (va - ro_mo)
def va_of(off): return ro_mo + (off - ro_fo)

CRIT_LO, CRIT_HI = 0x3d0e8e9, 0x3d2551d               # 파일 오프셋
CRIT_VA_LO, CRIT_VA_HI = va_of(CRIT_LO), va_of(CRIT_HI)
DYN_LO, DYN_HI = 0x2aafb79, 0x3d2551d                 # 풀 배제용(동적구조 전체)

# ---- 죽은풀(동적구조 전체 밖, SAFE_REDIRECT 기준) ----
tgt = set()
for seg_fo, seg_sz in ((ro_fo, ro_sz), (da_fo, da_sz)):
    n = seg_sz // 8
    arr = np.frombuffer(bytes(orig[seg_fo:seg_fo+n*8]), dtype='<u8')
    for i in np.nonzero((arr >= ro_lo) & (arr < ro_hi))[0]:
        tgt.add(int(arr[i]))
tgt_sorted = np.array(sorted(tgt), dtype='<u8')
txt = np.frombuffer(orig[tx_fo:tx_fo+(tx_sz//4)*4], dtype='<u4')
code_pages = set()
for mask, kind in ((np.uint32(0x90000000), 'adrp'), (np.uint32(0x10000000), 'adr')):
    sel = (txt & np.uint32(0x9F000000)) == mask
    for i in np.nonzero(sel)[0]:
        w = int(txt[i]); pc = tx_mo + int(i)*4
        imm = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 3)
        if imm & (1 << 20): imm -= (1 << 21)
        if kind == 'adrp':
            tp = ((pc >> 12) << 12) + (imm << 12)
            if ro_lo - 0x1000 <= tp < ro_hi: code_pages.add(tp >> 12)
        else:
            ta = pc + imm
            if ro_lo <= ta < ro_hi: code_pages.add(ta >> 12)
pool = []
i = 0
while i < ro_sz:
    if orig[ro_fo+i] == 0:
        j = i
        while j < ro_sz and orig[ro_fo+j] == 0: j += 1
        if j - i >= 24 and (ro_fo + j <= DYN_LO or ro_fo + i >= DYN_HI):   # ★동적구조 전체 배제
            s_va = ro_mo + i; e_va = ro_mo + j
            lo = int(np.searchsorted(tgt_sorted, s_va)); hi = int(np.searchsorted(tgt_sorted, e_va))
            has_code = any((p in code_pages) for p in range(s_va >> 12, ((e_va-1) >> 12)+1))
            if hi == lo and not has_code:
                a = i + 8; ln = (j - 8) - (i + 8)
                if ln >= 8:
                    seg = data[ro_fo+a: ro_fo+a+ln]
                    pos = 0
                    while pos < ln:
                        if seg[pos] != 0: pos += 1; continue
                        j2 = pos
                        while j2 < ln and seg[j2] == 0: j2 += 1
                        if j2 - pos >= 12: pool.append([a + pos + 1, (j2 - pos) - 2])
                        pos = j2
        i = j
    else:
        i += 1
pool.sort(key=lambda r: -r[1])
print(f"안전풀(동적구조 밖): {sum(r[1] for r in pool):,}B")
def alloc(need):
    for r in pool:
        if r[1] >= need:
            p = r[0]; r[0] += need; r[1] -= need; return p
    return None

# ---- 크리티컬을 가리키는 '변경된' 포인터 수집 ----
raw = bytes(data)
L = (len(raw) - 8) // 8 * 8
locs = []
for sh in range(8):
    v = np.frombuffer(raw[sh:sh+L], dtype='<u8')
    vo = np.frombuffer(orig[sh:sh+L], dtype='<u8')
    sel = (v >= np.uint64(CRIT_VA_LO)) & (v < np.uint64(CRIT_VA_HI)) & (v != vo)
    for i in np.nonzero(sel)[0]:
        locs.append((sh + int(i)*8, int(v[i])))
print(f"크리티컬을 가리키는 변경 포인터: {len(locs)}")

# ---- 이주(공유 dedup) + 복원 ----
cache = {}
fixed = reverted = 0
for loc, tva in locs:
    if tva in cache:
        struct.pack_into('<Q', data, loc, cache[tva]); fixed += 1; continue
    o = off_of(tva); e = data.find(b'\x00', o, o + 1200)
    sb = bytes(data[o:e]) if e > o else b''
    pos = alloc(len(sb) + 1) if (0 < len(sb) <= 1024) else None
    if pos is None:
        # 문자열 경계 불명/풀부족 → 이 포인터를 원본 값으로 복원(해당 조각만 개선 포기, 안전)
        data[loc:loc+8] = orig[loc:loc+8]; reverted += 1; continue
    nfo = ro_fo + pos
    data[nfo:nfo+len(sb)] = sb; data[nfo+len(sb)] = 0
    nva = va_of(nfo); cache[tva] = nva
    struct.pack_into('<Q', data, loc, nva); fixed += 1
print(f"이주 {fixed} (고유 {len(cache)}), 원본복원 {reverted}")

# ---- 크리티컬 원본 복원 ----
data[CRIT_LO:CRIT_HI] = orig[CRIT_LO:CRIT_HI]

# ---- 검증 ----
an = np.frombuffer(bytes(data), dtype=np.uint8); ao = np.frombuffer(orig, dtype=np.uint8)
crit_diff = int((ao[CRIT_LO:CRIT_HI] != an[CRIT_LO:CRIT_HI]).sum())
raw2 = bytes(data); nbad = 0
for sh in range(8):
    v = np.frombuffer(raw2[sh:sh+L], dtype='<u8')
    vo = np.frombuffer(orig[sh:sh+L], dtype='<u8')
    nbad += int(((v >= np.uint64(CRIT_VA_LO)) & (v < np.uint64(CRIT_VA_HI)) & (v != vo)).sum())
diff = np.nonzero(ao != an)[0]
in_tx = int(((diff >= tx_fo) & (diff < tx_fo + tx_sz)).sum())
in_hdr = int((diff < 0x100).sum())
print(f"크리티컬 원본대비 diff: {crit_diff} (0이어야)")
print(f"크리티컬 가리키는 변경포인터 잔여: {nbad} (0이어야)")
print(f"총 변경 {len(diff):,}B: .text={in_tx} 헤더={in_hdr}")
assert crit_diff == 0 and nbad == 0 and in_tx == 0 and in_hdr == 0 and len(data) == len(orig)
open('inject_out/main-safe17', 'wb').write(bytes(data))
print("저장 inject_out/main-safe17")
