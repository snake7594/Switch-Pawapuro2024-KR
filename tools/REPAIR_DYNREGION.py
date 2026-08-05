# -*- coding: utf-8 -*-
"""main-safe15 → main-safe16: 동적 링킹 구조 침범 수리.
- 금지영역 = [RELA 시작, STRTAB 끝] 파일 오프셋 [0x2aafb79, 0x3d2551d]
- safe7과 다른(=safe9+ 신규 풀 기록) 금지영역 바이트를 찾아:
  · 그 문자열을 가리키는 포인터(바이트 단위 스캔) 확보
  · 안전영역(0x3d2551d 이후의 죽은풀)에 재할당 → 포인터 갱신
  · 금지영역 바이트를 원본으로 복원
- safe4/7의 RELA 널섬 기록(검증된 안정)은 유지."""
import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

orig = open(r'!exefs-작업/main-원본', 'rb').read()
base7 = open('inject_out/main-safe7', 'rb').read()
data = bytearray(open('inject_out/main-safe15', 'rb').read())
tx_fo, tx_mo, tx_sz = struct.unpack_from('<III', orig, 0x10)
ro_fo, ro_mo, ro_sz = struct.unpack_from('<III', orig, 0x20)
da_fo, da_mo, da_sz = struct.unpack_from('<III', orig, 0x30)
ro_lo, ro_hi = ro_mo, ro_mo + ro_sz
DYN_LO, DYN_HI = 0x2aafb79, 0x3d2551d     # 파일 오프셋(동적구조 전체)
def off_of(va): return ro_fo + (va - ro_mo)
def va_of(off): return ro_mo + (off - ro_fo)

# ---- 안전영역 풀(금지영역 밖 + 기존 기준) ----
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
        if j - i >= 24 and ro_fo + i > DYN_HI:          # ★ 금지영역 이후만
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
print(f"안전 풀(금지영역 밖): {sum(r[1] for r in pool):,}B")
def alloc(need):
    for r in pool:
        if r[1] >= need:
            p = r[0]; r[0] += need; r[1] -= need; return p
    return None

# ---- 금지영역 내 safe7 대비 신규 기록(문자열) 수집 ----
o7 = np.frombuffer(base7, dtype=np.uint8)
cu = np.frombuffer(bytes(data), dtype=np.uint8)
seg_diff = np.nonzero(o7[DYN_LO:DYN_HI] != cu[DYN_LO:DYN_HI])[0]
print(f"금지영역 내 safe7 대비 diff: {len(seg_diff):,}B")
# diff 바이트 → 문자열 시작으로 확장(NUL 경계)
starts = set()
for d in seg_diff:
    p = DYN_LO + int(d)
    st = p
    while st > DYN_LO and data[st-1] != 0: st -= 1
    starts.add(st)
print(f"침범 문자열 수: {len(starts)}")

# ---- 각 문자열의 포인터(바이트 단위) 찾기 ----
victims = sorted(starts)
victim_vas = np.array([va_of(s) for s in victims], dtype=np.uint64)
ptr_locs = {v: [] for v in victims}
L = (len(data) - 8) // 8 * 8
raw = bytes(data)
vv_sorted = np.sort(victim_vas)
va2off = {va_of(s): s for s in victims}
for sh in range(8):
    view = np.frombuffer(raw[sh:sh+L], dtype='<u8')
    sel = np.isin(view, vv_sorted)
    for i in np.nonzero(sel)[0]:
        va = int(view[i])
        ptr_locs[va2off[va]].append(sh + int(i)*8)
n_ptr = sum(len(v) for v in ptr_locs.values())
print(f"포인터 참조: {n_ptr}")

# ---- 이주 + 복원 ----
moved = orphan = fail = 0
for st in victims:
    e = data.find(b'\x00', st)
    sbytes = bytes(data[st:e])
    locs = ptr_locs[st]
    if locs:
        pos = alloc(len(sbytes) + 1)
        if pos is None:
            fail += 1; continue
        nfo = ro_fo + pos
        data[nfo:nfo+len(sbytes)] = sbytes; data[nfo+len(sbytes)] = 0
        nva = va_of(nfo)
        for lo_ in locs:
            struct.pack_into('<Q', data, lo_, nva)
        moved += 1
    else:
        orphan += 1
    # 원본 복원(문자열 구간 + 종료 NUL 자리)
    data[st:e+1] = orig[st:e+1]
print(f"이주 {moved}, 고아(참조없음→복원만) {orphan}, 풀부족 {fail}")

# 잔여 diff 재확인(전체 금지영역을 safe7 상태로 맞춤: 남은 diff는 safe7과 동일해야)
cu2 = np.frombuffer(bytes(data), dtype=np.uint8)
rem = np.nonzero(o7[DYN_LO:DYN_HI] != cu2[DYN_LO:DYN_HI])[0]
print(f"수리 후 금지영역 safe7 대비 잔여 diff: {len(rem)}")
if len(rem):
    # 남은 것은 강제 복원(안전 우선: safe7 바이트로)
    for d in rem:
        p = DYN_LO + int(d)
        data[p] = base7[p]
    cu3 = np.frombuffer(bytes(data), dtype=np.uint8)
    rem2 = np.nonzero(o7[DYN_LO:DYN_HI] != cu3[DYN_LO:DYN_HI])[0]
    print(f"강제 복원 후 잔여: {len(rem2)}")

# ---- 검증 ----
an = np.frombuffer(bytes(data), dtype=np.uint8); ao = np.frombuffer(orig, dtype=np.uint8)
diff = np.nonzero(ao != an)[0]
in_tx = int(((diff >= tx_fo) & (diff < tx_fo + tx_sz)).sum())
in_hdr = int((diff < 0x100).sum())
mn, mx = (int(diff[0]), int(diff[-1])) if len(diff) else (0, 0)
print(f"원본 대비 총 변경 {len(diff):,}B (0x{mn:x}~0x{mx:x}): .text={in_tx} 헤더={in_hdr}")
assert in_tx == 0 and in_hdr == 0 and len(data) == len(orig)
open('inject_out/main-safe16', 'wb').write(bytes(data))
print("저장 inject_out/main-safe16")
