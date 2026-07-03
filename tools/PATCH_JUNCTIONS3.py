# -*- coding: utf-8 -*-
"""main-safe10 → main-safe11: 확장 풀(RES=8, >=24B zero-run)로 P1 잔여 완결.
안전 기준 동일: 데이터포인터 타겟 run 배제, ADRP/ADR 코드 페이지 배제, 현재도 0인 구간만 사용."""
import sys, os, json, struct
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r"C:\Users\Jae Ho Lee\Desktop\z\실황2024")
import numpy as np

orig = open('!exefs-작업/main-원본', 'rb').read()
data = bytearray(open('inject_out/main-safe10', 'rb').read())
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
RES = 8; MINRUN = 24
pool = []
i = 0
while i < ro_sz:
    if orig[ro_fo+i] == 0:
        j = i
        while j < ro_sz and orig[ro_fo+j] == 0: j += 1
        if j - i >= MINRUN:
            s_va = ro_mo + i; e_va = ro_mo + j
            lo = int(np.searchsorted(tgt_sorted, s_va)); hi = int(np.searchsorted(tgt_sorted, e_va))
            has_code = any((p in code_pages) for p in range(s_va >> 12, ((e_va-1) >> 12)+1))
            if hi == lo and not has_code:
                a = i + RES; ln = (j - RES) - (i + RES)
                # 현재(safe10) 기준 0 유지되는 최장 꼬리 구간
                if ln >= 8:
                    seg = data[ro_fo+a: ro_fo+a+ln]
                    last_nz = -1
                    for k2 in range(ln-1, -1, -1):
                        if seg[k2] != 0: last_nz = k2; break
                    free_a = a + last_nz + 2
                    free_ln = ln - (last_nz + 2)
                    if free_ln >= 8: pool.append([free_a, free_ln])
        i = j
    else:
        i += 1
pool.sort(key=lambda r: -r[1])
print(f"확장 풀: {len(pool)} runs, {sum(r[1] for r in pool):,}B")
def alloc(need):
    for r in pool:
        if r[1] >= need:
            pos = r[0]; r[0] += need; r[1] -= need; return pos
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

runs = json.load(open('_script_runs.json'))
n_fix = n_fail = 0
for a, b in runs:
    n = (b - a)//24 + 1
    if n < 2: continue
    jps = [read_orig_rec(a + 24*k) for k in range(n)]
    prose = sum(1 for j in jps if j and j.endswith(('。', '！', '？'))) >= 1 and \
            any(j and len(j) >= 10 and any(hira(c) for c in j) and any(kanji(c) for c in j) for j in jps)
    if not prose: continue
    for k in range(n - 1):
        jpA, jpB = jps[k], jps[k+1]
        if not jpA or not jpB: continue
        if not (jpA.endswith(('。', '！', '？')) and len(jpB) >= 4): continue
        recA = a + 24*k
        ko, o, budget = read_rec(recA)
        if not ko or not ko.endswith(('.', '!', '?', '…', '。')) or ko.endswith(' '): continue
        nb = enc(ko + ' ')
        region = budget + 1
        if len(nb) <= region - 1:
            data[o:o+len(nb)] = nb
            data[o+len(nb):o+region] = b'\x00' * (region - len(nb))
            n_fix += 1
        else:
            pos = alloc(len(nb) + 1)
            if pos is None: n_fail += 1; continue
            nfo = ro_fo + pos
            data[nfo:nfo+len(nb)] = nb; data[nfo+len(nb)] = 0
            struct.pack_into('<Q', data, recA, va_of(nfo))
            n_fix += 1
print(f"P1 잔여 처리: {n_fix}건, 실패 {n_fail}")

an = np.frombuffer(bytes(data), dtype=np.uint8); ao = np.frombuffer(orig, dtype=np.uint8)
diff = np.nonzero(ao != an)[0]
in_tx = int(((diff >= tx_fo) & (diff < tx_fo + tx_sz)).sum())
in_hdr = int((diff < 0x100).sum())
print(f"원본 대비 변경 {len(diff):,}B: .text={in_tx} 헤더={in_hdr}")
assert in_tx == 0 and in_hdr == 0 and len(data) == len(orig)
open('inject_out/main-safe11', 'wb').write(data)
print("저장 inject_out/main-safe11")
