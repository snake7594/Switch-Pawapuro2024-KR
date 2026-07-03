# -*- coding: utf-8 -*-
"""main-safe13 → main-safe14: 공백 패스 멱등 재실행(S2 접합 + P1 문장경계), GC 풀 사용."""
import sys, os, json, struct
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r"C:\Users\Jae Ho Lee\Desktop\z\실황2024")
import numpy as np

orig = open('!exefs-작업/main-원본', 'rb').read()
data = bytearray(open('inject_out/main-safe13', 'rb').read())
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

# 풀(GC 포함) — APPLY_RUBY_LINES와 동일
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
print(f"GC {n_gc}, 풀 {sum(r[1] for r in pool):,}B")
def alloc(need):
    for r in pool:
        if r[1] >= need:
            p = r[0]; r[0] += need; r[1] -= need; return p
    return None

def read_rec(rec):
    va = struct.unpack_from('<Q', data, rec)[0]
    if not (ro_lo <= va < ro_hi): return None, None, 0
    o = off_of(va); e = data.find(b'\x00', o)
    if e <= o: return '', o, 0
    b = bytes(data[o:e])
    T = 0; k = e
    while k < len(data) and data[k] == 0: T += 1; k += 1
    return dec(b), o, (e - o) + (T - 1 if T > 0 else 0)
def read_orig_rec(rec):
    va = struct.unpack_from('<Q', orig, rec)[0]
    if not (ro_lo <= va < ro_hi): return None
    o = off_of(va); e = orig.find(b'\x00', o)
    try: return orig[o:e].decode('utf-8')
    except UnicodeDecodeError: return None
def hira(c): return '぀' <= c <= 'ゟ'
def kanji(c): return '一' <= c <= '鿿' or c == '々'

def add_space(rec):
    ko, o, budget = read_rec(rec)
    if not ko or not any('가' <= c <= '힣' for c in ko): return 0
    if ko.endswith((' ', '　', '(', '「', '（', '[')): return 0
    nb = enc(ko + ' ')
    region = budget + 1
    if len(nb) <= region - 1:
        data[o:o+len(nb)] = nb
        data[o+len(nb):o+region] = b'\x00' * (region - len(nb))
        return 1
    pos = alloc(len(nb) + 1)
    if pos is None: return -1
    nfo = ro_fo + pos
    data[nfo:nfo+len(nb)] = nb; data[nfo+len(nb)] = 0
    struct.pack_into('<Q', data, rec, va_of(nfo))
    return 1

# S2 재실행(접합 v4)
juncs = json.load(open('_junctions_v4.json', encoding='utf-8'))
s2 = s2f = 0
for j in juncs:
    r = add_space(j['recA'])
    if r == 1: s2 += 1
    elif r == -1: s2f += 1
# P1 재실행(문장경계)
runs = json.load(open('_script_runs.json'))
p1 = p1f = 0
for a, b in runs:
    n = (b - a)//24 + 1
    if n < 2: continue
    jps = [read_orig_rec(a + 24*k) for k in range(n)]
    prose = sum(1 for jj in jps if jj and jj.endswith(('。', '！', '？'))) >= 1 and \
            any(jj and len(jj) >= 10 and any(hira(c) for c in jj) and any(kanji(c) for c in jj) for jj in jps)
    if not prose: continue
    for k in range(n - 1):
        jpA, jpB = jps[k], jps[k+1]
        if not jpA or not jpB: continue
        if not (jpA.endswith(('。', '！', '？')) and len(jpB) >= 4): continue
        ko, o, budget = read_rec(a + 24*k)
        if not ko or not ko.endswith(('.', '!', '?', '…', '。')) or ko.endswith(' '): continue
        r = add_space(a + 24*k)
        if r == 1: p1 += 1
        elif r == -1: p1f += 1
print(f"S2 재실행: +{s2} (실패 {s2f}), P1 재실행: +{p1} (실패 {p1f})")

an = np.frombuffer(bytes(data), dtype=np.uint8); ao = np.frombuffer(orig, dtype=np.uint8)
diff = np.nonzero(ao != an)[0]
in_tx = int(((diff >= tx_fo) & (diff < tx_fo + tx_sz)).sum())
in_hdr = int((diff < 0x100).sum())
print(f"원본 대비 변경 {len(diff):,}B: .text={in_tx} 헤더={in_hdr}")
assert in_tx == 0 and in_hdr == 0 and len(data) == len(orig)
open('inject_out/main-safe14', 'wb').write(data)
print("저장 inject_out/main-safe14")
