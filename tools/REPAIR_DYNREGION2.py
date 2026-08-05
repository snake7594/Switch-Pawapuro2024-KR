# -*- coding: utf-8 -*-
"""safe16 2차 수리: 동적구조 영역을 아직 가리키는 safe9+ 포인터 복구.
- 대상: safe16의 8B 값이 dyn VA 범위를 가리키고, safe7의 같은 위치 값과 다른 곳(=safe9+에서 기록된 포인터)
- 복구: safe15에서 그 포인터의 문자열 바이트를 회수 → 안전 풀(DYN 이후)에 기록 → 포인터 갱신
출력: main-safe16(갱신)"""
import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

orig = open(r'!exefs-작업/main-원본', 'rb').read()
s7 = open('inject_out/main-safe7', 'rb').read()
s15 = open('inject_out/main-safe15', 'rb').read()
data = bytearray(open('inject_out/main-safe16', 'rb').read())
tx_fo, tx_mo, tx_sz = struct.unpack_from('<III', orig, 0x10)
ro_fo, ro_mo, ro_sz = struct.unpack_from('<III', orig, 0x20)
da_fo, da_mo, da_sz = struct.unpack_from('<III', orig, 0x30)
ro_lo, ro_hi = ro_mo, ro_mo + ro_sz
DYN_LO, DYN_HI = 0x2aafb79, 0x3d2551d
DYN_VA_LO, DYN_VA_HI = ro_mo + (DYN_LO - ro_fo), ro_mo + (DYN_HI - ro_fo)
def off_of(va): return ro_fo + (va - ro_mo)
def va_of(off): return ro_mo + (off - ro_fo)

# 안전 풀(DYN 이후, 기존 기준) — safe16 현재 상태 기준 잔여 갭
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
        if j - i >= 24 and ro_fo + i > DYN_HI:
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
print(f"안전 풀 잔여: {sum(r[1] for r in pool):,}B")
def alloc(need):
    for r in pool:
        if r[1] >= need:
            p = r[0]; r[0] += need; r[1] -= need; return p
    return None

# ---- dyn 영역을 가리키는 safe9+ 포인터 위치 수집 ----
raw16 = bytes(data)
L = (len(raw16) - 8) // 8 * 8
locs = []
for sh in range(8):
    v16 = np.frombuffer(raw16[sh:sh+L], dtype='<u8')
    v7 = np.frombuffer(s7[sh:sh+L], dtype='<u8')
    sel = (v16 >= np.uint64(DYN_VA_LO)) & (v16 < np.uint64(DYN_VA_HI)) & (v16 != v7)
    for i in np.nonzero(sel)[0]:
        locs.append((sh + int(i)*8, int(v16[i])))
print(f"safe9+ dyn 포인터: {len(locs)}")

# ---- 복구: safe15에서 문자열 회수 → 안전 풀 재배치 ----
cache = {}
fixed = fail = 0
for loc, tva in locs:
    if tva in cache:
        struct.pack_into('<Q', data, loc, cache[tva]); fixed += 1; continue
    o15 = off_of(tva)
    e15 = s15.find(b'\x00', o15)
    sb = s15[o15:e15]
    if not (0 < len(sb) <= 512):
        fail += 1; continue
    pos = alloc(len(sb) + 1)
    if pos is None: fail += 1; continue
    nfo = ro_fo + pos
    data[nfo:nfo+len(sb)] = sb; data[nfo+len(sb)] = 0
    nva = va_of(nfo)
    cache[tva] = nva
    struct.pack_into('<Q', data, loc, nva)
    fixed += 1
print(f"복구 {fixed} (고유 문자열 {len(cache)}), 실패 {fail}")

# ---- 최종 검증 ----
an = np.frombuffer(bytes(data), dtype=np.uint8)
ao = np.frombuffer(orig, dtype=np.uint8)
o7 = np.frombuffer(s7, dtype=np.uint8)
# 1) 금지영역은 safe7과 동일해야
rem = np.nonzero(o7[DYN_LO:DYN_HI] != an[DYN_LO:DYN_HI])[0]
print(f"금지영역 safe7 대비 diff: {len(rem)} (0이어야)")
# 2) 이제 dyn을 가리키는 safe9+ 포인터가 없어야
raw = bytes(data)
n_bad = 0
for sh in range(8):
    v16 = np.frombuffer(raw[sh:sh+L], dtype='<u8')
    v7 = np.frombuffer(s7[sh:sh+L], dtype='<u8')
    sel = (v16 >= np.uint64(DYN_VA_LO)) & (v16 < np.uint64(DYN_VA_HI)) & (v16 != v7)
    n_bad += int(sel.sum())
print(f"잔여 dyn 신규 포인터: {n_bad} (0이어야)")
in_tx = int((np.nonzero(ao != an)[0] < tx_fo + tx_sz).sum() - (np.nonzero(ao != an)[0] < tx_fo).sum())
diff = np.nonzero(ao != an)[0]
in_tx = int(((diff >= tx_fo) & (diff < tx_fo + tx_sz)).sum())
in_hdr = int((diff < 0x100).sum())
print(f"총 변경 {len(diff):,}B: .text={in_tx} 헤더={in_hdr}")
assert in_tx == 0 and in_hdr == 0 and len(rem) == 0 and n_bad == 0
open('inject_out/main-safe16', 'wb').write(bytes(data))
print("main-safe16 갱신 저장")
