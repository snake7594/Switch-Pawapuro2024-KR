# -*- coding: utf-8 -*-
"""main-safe12 → main-safe13:
A) 루비 동사분절 통합: R레코드→빈문자열 포인터, C레코드→풀의 통합구(공유보호)
B) 줄폭 수정: reflow(공백↔개행 재배치)·압축 번역을 exe 문자열에 적용(제자리+슬랙, de-spaced 내용 매칭)
"""
import sys, os, json, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

orig = open('!exefs-작업/main-원본', 'rb').read()
data = bytearray(open('inject_out/main-safe12', 'rb').read())
tx_fo, tx_mo, tx_sz = struct.unpack_from('<III', orig, 0x10)
ro_fo, ro_mo, ro_sz = struct.unpack_from('<III', orig, 0x20)
da_fo, da_mo, da_sz = struct.unpack_from('<III', orig, 0x30)
ro_lo, ro_hi = ro_mo, ro_mo + ro_sz

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv(); TSV_R = {v: k for k, v in TSV.items()}
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')
def dec(b):
    try: s = b.decode('utf-8')
    except UnicodeDecodeError: return None
    return ''.join(TSV_R.get(c, c) for c in s)
def off_of(va): return ro_fo + (va - ro_mo)
def va_of(off): return ro_mo + (off - ro_fo)

# ---- 풀(GC 포함) ----
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
regions = []
i = 0
while i < ro_sz:
    if orig[ro_fo+i] == 0:
        j = i
        while j < ro_sz and orig[ro_fo+j] == 0: j += 1
        if j - i >= 24:
            s_va = ro_mo + i; e_va = ro_mo + j
            lo = int(np.searchsorted(tgt_sorted, s_va)); hi = int(np.searchsorted(tgt_sorted, e_va))
            has_code = any((p in code_pages) for p in range(s_va >> 12, ((e_va-1) >> 12)+1))
            if hi == lo and not has_code:
                a = i + 8; ln = (j - 8) - (i + 8)
                if ln >= 8: regions.append((a, ln))
        i = j
    else:
        i += 1
# GC
region_starts = np.array([ro_mo + a for a, ln in regions], dtype=np.uint64)
region_ends = np.array([ro_mo + a + ln for a, ln in regions], dtype=np.uint64)
pointed = set()
L = (len(data) - 8) // 8 * 8
for sh in range(8):
    view = np.frombuffer(bytes(data[sh:sh + L]), dtype='<u8')
    sel = (view >= np.uint64(ro_mo)) & (view < np.uint64(ro_mo + ro_sz))
    vals = view[sel]
    if len(vals) == 0: continue
    idx = np.searchsorted(region_starts, vals, side='right') - 1
    ok = (idx >= 0) & (vals < region_ends[np.clip(idx, 0, len(regions)-1)])
    for v in vals[ok]: pointed.add(int(v))
n_gc = 0
for a, ln in regions:
    o = ro_fo + a; end = o + ln
    pos = o
    while pos < end:
        if data[pos] == 0: pos += 1; continue
        e = data.find(b'\x00', pos, end)
        if e < 0: e = end
        if va_of(pos) not in pointed:
            data[pos:e] = b'\x00' * (e - pos); n_gc += 1
        pos = e + 1
pool = []
for a, ln in regions:
    o = ro_fo + a; end = o + ln
    pos = o
    while pos < end:
        if data[pos] != 0: pos += 1; continue
        j2 = pos
        while j2 < end and data[j2] == 0: j2 += 1
        if j2 - pos >= 12: pool.append([pos - ro_fo + 1, (j2 - pos) - 2])
        pos = j2
pool.sort(key=lambda r: -r[1])
print(f"GC {n_gc}개, 풀 {sum(r[1] for r in pool):,}B")
def alloc(need):
    for r in pool:
        if r[1] >= need:
            p = r[0]; r[0] += need; r[1] -= need; return p
    return None

# 빈 문자열 VA (모든 빈 R이 공유)
empty_pos = alloc(2)
data[ro_fo+empty_pos] = 0
EMPTY_VA = va_of(ro_fo + empty_pos)

# ---- A) 루비 통합 (검증 패스 산출: {i, mode:'a'|'b', ko}) ----
review = json.load(open('_rubysplit_review.json', encoding='utf-8'))
ver = {r['i']: r for r in json.load(open('_ruby_verified.json', encoding='utf-8'))}
strcache = {}
def pool_str(ko):
    if ko in strcache: return strcache[ko]
    nb = enc(ko)
    pos = alloc(len(nb) + 1)
    if pos is None: return None
    nfo = ro_fo + pos
    data[nfo:nfo+len(nb)] = nb; data[nfo+len(nb)] = 0
    strcache[ko] = va_of(nfo)
    return strcache[ko]
nA = nAf = nModeA = nModeB = 0
for it in review:
    v = ver.get(it['i'])
    if not v: nAf += 1; continue
    ko = (v.get('ko') or '').strip()
    mode = v.get('mode', 'a')
    if not ko or any('぀' <= c <= 'ヿ' for c in ko): nAf += 1; continue
    va = pool_str(ko)
    if va is None: nAf += 1; continue
    for (recR, recC, budR, budC) in it['occ']:
        if mode == 'a':
            struct.pack_into('<Q', data, recR, EMPTY_VA); nModeA += 1
        else:
            nModeB += 1
        struct.pack_into('<Q', data, recC, va)
        nA += 1
print(f"A) 루비 통합: {nA} 접합 적용(모드a {nModeA}/b {nModeB}), 실패/누락 {nAf}")

# ---- B) 줄폭 수정 ----
def despace(s): return s.replace('\n', '').replace(' ', '').replace('　', '')
doc = json.load(open('번역_일본어.json', encoding='utf-8'))
comp_old = json.load(open('_linewidth_comp.json', encoding='utf-8'))
comp_new = {r['i']: (r.get('ko') or '').strip() for r in json.load(open('_linecomp_fix.json', encoding='utf-8'))}
# 압축 결과 JSON 반영
jp2new = {}
for o in comp_old:
    nk = comp_new.get(o['i'])
    if nk: jp2new[o['jp']] = (despace(o['ko']), nk)
nB = nBf = 0
def width(s):
    w = 0
    for c in s:
        oc = ord(c)
        w += 1 if (oc < 0x1100 or (0xFF61 <= oc <= 0xFFDC)) else 2
    return w
for s in doc['strings']:
    jp = s['jp']; ko = s.get('ko', '').strip()
    if '\n' not in jp or not ko: continue
    occ = [o for o in s.get('occurrences', []) if o['method'] == 'exe']
    if not occ: continue
    if jp in jp2new:
        old_ds, new_ko = jp2new[jp]
        s['ko'] = new_ko
    else:
        jl = jp.split('\n'); kl = ko.split('\n')
        if max(width(x) for x in kl) <= max(width(x) for x in jl) + 2: continue
        old_ds, new_ko = despace(ko), ko   # reflow 반영분(내용 동일)
    nb = enc(new_ko)
    for o in occ:
        off = o['offset']
        e = data.find(b'\x00', off)
        if e <= off: continue
        curko = dec(bytes(data[off:e]))
        if curko is None: continue
        if despace(curko) != old_ds and not old_ds.startswith(despace(curko)): continue
        T = 0; k = e
        while k < len(data) and data[k] == 0: T += 1; k += 1
        region = (e - off) + T
        wb = nb
        if len(wb) > region - 1:
            wb = wb[:region-1]
            while wb:
                try: wb.decode('utf-8'); break
                except UnicodeDecodeError: wb = wb[:-1]
        data[off:off+len(wb)] = wb
        data[off+len(wb):off+region] = b'\x00' * (region - len(wb))
        nB += 1
json.dump(doc, open('번역_일본어.json', 'w', encoding='utf-8'), ensure_ascii=False)
print(f"B) 줄폭 수정 적용: {nB} occ")

an = np.frombuffer(bytes(data), dtype=np.uint8); ao = np.frombuffer(orig, dtype=np.uint8)
diff = np.nonzero(ao != an)[0]
in_tx = int(((diff >= tx_fo) & (diff < tx_fo + tx_sz)).sum())
in_hdr = int((diff < 0x100).sum())
print(f"원본 대비 변경 {len(diff):,}B: .text={in_tx} 헤더={in_hdr}")
assert in_tx == 0 and in_hdr == 0 and len(data) == len(orig)
open('inject_out/main-safe13', 'wb').write(data)
print("저장 inject_out/main-safe13")
