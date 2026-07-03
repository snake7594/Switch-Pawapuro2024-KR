# -*- coding: utf-8 -*-
"""main-safe9 → main-safe10: 접합부 후속 정비.
P1) 문장 경계 공백: jpA가 。！？로 끝나고 다음 레코드가 산문 → koA(./!/? 끝)에 후행 공백
P2) 조사 일치: [명사 레코드 N]+[조사로 시작하는 꼬리 C]에서 N의 받침에 맞게 C 선두 조사 교정
    (은/는, 이/가, 을/를, 와/과, 로/으로) — C는 공유 가능성 때문에 항상 풀 재배치(원본 문자열 보존)
"""
import sys, os, json, struct
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r"C:\Users\Jae Ho Lee\Desktop\z\실황2024")
import numpy as np

orig = open('!exefs-작업/main-원본', 'rb').read()
data = bytearray(open('inject_out/main-safe9', 'rb').read())
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

# ---- 죽은풀 잔여(safe9 기준 재산출; SAFE_REDIRECT 기준 동일) ----
from collections import defaultdict
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
RES = 32; MINRUN = 64
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
print(f"풀 잔여: {sum(r[1] for r in pool):,}B")
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
def read_orig_str(rec):
    va = struct.unpack_from('<Q', orig, rec)[0]
    if not (ro_lo <= va < ro_hi): return None
    o = off_of(va); e = orig.find(b'\x00', o)
    try: return orig[o:e].decode('utf-8')
    except UnicodeDecodeError: return None
def write_str_at(o, region, nb):
    data[o:o+len(nb)] = nb
    data[o+len(nb):o+region] = b'\x00' * (region - len(nb))

def hira(c): return '぀' <= c <= 'ゟ'
def kanji(c): return '一' <= c <= '鿿' or c == '々'
def kata(c): return '゠' <= c <= 'ヿ' or c == 'ー'
def batchim(c):
    v = ord(c) - 0xAC00
    return 0 <= v <= 11171 and v % 28 != 0
def rieul(c):
    v = ord(c) - 0xAC00
    return 0 <= v <= 11171 and v % 28 == 8   # ㄹ받침

runs = json.load(open('_script_runs.json'))
n_p1 = n_p1pool = n_p2 = skip = 0
for a, b in runs:
    n = (b - a)//24 + 1
    if n < 2: continue
    jps = []
    for k in range(n):
        jps.append(read_orig_str(a + 24*k))
    # 산문성: 문장종결 1+ & 가나 시작 1+ (혹은 긴 산문 레코드)
    prose = sum(1 for j in jps if j and j.endswith(('。', '！', '？'))) >= 1 and \
            any(j and len(j) >= 10 and any(hira(c) for c in j) and any(kanji(c) for c in j) for j in jps)
    if not prose: continue
    for k in range(n - 1):
        jpA, jpB = jps[k], jps[k+1]
        if not jpA or not jpB: continue
        recA = a + 24*k; recB = a + 24*(k+1)
        # ---- P1: 문장 경계 공백 ----
        if jpA.endswith(('。', '！', '？')) and len(jpB) >= 4 and (any(hira(c) for c in jpB) or any(kanji(c) for c in jpB)):
            ko, o, budget = read_rec(recA)
            if ko and ko.endswith(('.', '!', '?', '…', '。')) and not ko.endswith(' '):
                nb = enc(ko + ' ')
                region = budget + 1
                if len(nb) <= region - 1:
                    write_str_at(o, region, nb); n_p1 += 1
                else:
                    pos = alloc(len(nb) + 1)
                    if pos is not None:
                        nfo = ro_fo + pos
                        data[nfo:nfo+len(nb)] = nb; data[nfo+len(nb)] = 0
                        struct.pack_into('<Q', data, recA, va_of(nfo))
                        n_p1pool += 1
        # ---- P2: 조사 일치 ----
        # N=명사 레코드(한자/가타 시작, 가나 없음, 짧음), C=다음 레코드 jp가 조사류 시작
        if k + 1 < n and jpB and (kanji(jpB[0]) or kata(jpB[0])) and len(jpB) <= 12 and not any(hira(c) for c in jpB):
            jpC = jps[k+2] if k + 2 < n else None
            if jpC and jpC[0] in 'はがをともの':
                koN, oN, bN = read_rec(recB)
                recC = a + 24*(k+2)
                koC, oC, bC = read_rec(recC)
                if koN and koC and any('가' <= c <= '힣' for c in koN):
                    last = koN.rstrip()[-1:]
                    if not ('가' <= last <= '힣'): continue
                    bt = batchim(last); rl = rieul(last)
                    fix = None
                    if koC[:1] == '은' and not bt: fix = '는' + koC[1:]
                    elif koC[:1] == '는' and bt: fix = '은' + koC[1:]
                    elif koC[:1] == '이' and not bt and len(koC) > 1 and koC[1] in ' 가에라는란': fix = '가' + koC[1:]
                    elif koC[:1] == '가' and bt: fix = '이' + koC[1:]
                    elif koC[:1] == '을' and not bt: fix = '를' + koC[1:]
                    elif koC[:1] == '를' and bt: fix = '을' + koC[1:]
                    elif koC[:1] == '와' and bt: fix = '과' + koC[1:]
                    elif koC[:1] == '과' and not bt: fix = '와' + koC[1:]
                    elif koC[:2] == '으로' and (not bt or rl): fix = '로' + koC[2:]
                    elif koC[:1] == '로' and koC[:2] != '로서' and bt and not rl: fix = '으로' + koC[1:]
                    if fix:
                        nb = enc(fix)
                        pos = alloc(len(nb) + 1)   # 공유 보호: 항상 풀
                        if pos is not None:
                            nfo = ro_fo + pos
                            data[nfo:nfo+len(nb)] = nb; data[nfo+len(nb)] = 0
                            struct.pack_into('<Q', data, recC, va_of(nfo))
                            n_p2 += 1
print(f"P1 문장경계 공백: 제자리 {n_p1} + 풀 {n_p1pool}, P2 조사교정: {n_p2}")

an = np.frombuffer(bytes(data), dtype=np.uint8); ao = np.frombuffer(orig, dtype=np.uint8)
diff = np.nonzero(ao != an)[0]
in_tx = int(((diff >= tx_fo) & (diff < tx_fo + tx_sz)).sum())
in_hdr = int((diff < 0x100).sum())
print(f"원본 대비 변경 {len(diff):,}B: .text={in_tx} 헤더={in_hdr}")
assert in_tx == 0 and in_hdr == 0 and len(data) == len(orig)
open('inject_out/main-safe10', 'wb').write(data)
print("저장 inject_out/main-safe10")
