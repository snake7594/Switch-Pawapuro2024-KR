# -*- coding: utf-8 -*-
"""main-safe8 → main-safe9: 연결 대사 접합부 정비.
S1) 루비 레코드('단어／よみ') 한국어에서 ／이후 일본어 읽기 제거(원본 jp 패턴 검증, 제자리 단축)
S2) 접합부(A=연결형끝 + B=명사시작) A 한국어에 후행 공백 추가
    - 슬랙 있으면 제자리, 없으면 SAFE_REDIRECT 죽은풀 잔여공간에 재배치+레코드 포인터 갱신
검증: .text/헤더 불변."""
import sys, os, json, struct, re
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

orig = open('!exefs-작업/main-원본', 'rb').read()
data = bytearray(open('inject_out/main-safe8', 'rb').read())
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

# ---- 죽은풀 재구성(SAFE_REDIRECT과 동일 기준) + 잔여공간 ----
from collections import defaultdict
pidx = defaultdict(list); tgt = set()
for seg_fo, seg_sz in ((ro_fo, ro_sz), (da_fo, da_sz)):
    n = seg_sz // 8
    arr = np.frombuffer(bytes(orig[seg_fo:seg_fo+n*8]), dtype='<u8')
    for i in np.nonzero((arr >= ro_lo) & (arr < ro_hi))[0]:
        v = int(arr[i]); tgt.add(v)
tgt_sorted = np.array(sorted(tgt), dtype='<u8')
txt = np.frombuffer(orig[tx_fo:tx_fo+(tx_sz//4)*4], dtype='<u4')
code_pages = set()
for mask, base in ((np.uint32(0x90000000), 'adrp'), (np.uint32(0x10000000), 'adr')):
    sel = (txt & np.uint32(0x9F000000)) == mask
    for i in np.nonzero(sel)[0]:
        w = int(txt[i]); pc = tx_mo + int(i)*4
        imm = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 3)
        if imm & (1 << 20): imm -= (1 << 21)
        if base == 'adrp':
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
                    # 현재(safe8)에서 아직 0인 꼬리 = 잔여공간
                    seg = data[ro_fo+a: ro_fo+a+ln]
                    last_nz = -1
                    for k2 in range(ln-1, -1, -1):
                        if seg[k2] != 0: last_nz = k2; break
                    free_a = a + last_nz + 2   # 종료 NUL + 1 여유
                    free_ln = ln - (last_nz + 2)
                    if free_ln >= 8: pool.append([free_a, free_ln])
        i = j
    else:
        i += 1
pool.sort(key=lambda r: -r[1])
print(f"죽은풀 잔여: {len(pool)} runs, {sum(r[1] for r in pool):,}B")
def alloc(need):
    for r in pool:
        if r[1] >= need:
            pos = r[0]; r[0] += need; r[1] -= need; return pos
    return None

def read_rec(rec):
    """레코드의 현재 포인터 → (ko문자열, str_off, budget)."""
    va = struct.unpack_from('<Q', data, rec)[0]
    if not (ro_lo <= va < ro_hi): return None, None, 0, va
    o = off_of(va); e = data.find(b'\x00', o)
    if e <= o: return '', o, 0, va
    b = bytes(data[o:e])
    T = 0; k = e
    while k < len(data) and data[k] == 0: T += 1; k += 1
    s = dec(b)
    return s, o, (e - o) + (T - 1 if T > 0 else 0), va

def write_str_at(o, region, nb):
    data[o:o+len(nb)] = nb
    data[o+len(nb):o+region] = b'\x00' * (region - len(nb))

# ---- S1: 루비 읽기 제거 ----
runs = json.load(open('_script_runs.json'))
ruby_pat = re.compile(r'^[^／]{1,10}／[぀-ゟー]{1,12}$')
def read_orig_str(va):
    o = off_of(va); e = orig.find(b'\x00', o)
    try: return orig[o:e].decode('utf-8')
    except UnicodeDecodeError: return None
n_ruby = 0; ruby_recs = []
seen_off = set()
for a, b in runs:
    n = (b - a)//24 + 1
    for k in range(n):
        rec = a + 24*k
        va0 = struct.unpack_from('<Q', orig, rec)[0]
        jp = read_orig_str(va0)
        if not jp or '／' not in jp or not ruby_pat.match(jp): continue
        ko, o, budget, cva = read_rec(rec)
        if ko is None or o in seen_off: continue
        seen_off.add(o)
        ruby_recs.append(rec)
        if '／' in ko:
            base = ko.split('／', 1)[0]
            if base:
                nb = enc(base)
                region = budget + 1
                if len(nb) <= region - 1:
                    write_str_at(o, region, nb); n_ruby += 1
print(f"S1 루비 읽기 제거: {n_ruby}건 (루비 레코드 {len(ruby_recs)})")

# ---- S2: 접합부 공백 ----
mech = json.load(open('_junc_mech.json', encoding='utf-8'))
josa = json.load(open('_junc_josa.json', encoding='utf-8'))
ruby_j = json.load(open('_junc_ruby.json', encoding='utf-8'))
# 대상 = mech + josa(공백만) + ruby 접합의 A측(공백)
targets = {}
juncs = json.load(open('_junctions_v4.json', encoding='utf-8'))
for j in juncs:
    targets[j['recA']] = True
n_sp = n_pool = n_skip = n_already = 0
for rec in sorted(targets):
    ko, o, budget, cva = read_rec(rec)
    if ko is None or not ko: n_skip += 1; continue
    if not any('가' <= c <= '힣' for c in ko): n_skip += 1; continue
    if ko.endswith((' ', '　', '(', '「', '（', '[')): n_already += 1; continue
    nb = enc(ko + ' ')
    region = budget + 1
    if len(nb) <= region - 1:
        write_str_at(o, region, nb); n_sp += 1
    else:
        pos = alloc(len(nb) + 1)
        if pos is None: n_skip += 1; continue
        nfo = ro_fo + pos
        data[nfo:nfo+len(nb)] = nb; data[nfo+len(nb)] = 0
        struct.pack_into('<Q', data, rec, va_of(nfo))
        n_pool += 1
print(f"S2 공백: 제자리 {n_sp}, 풀재배치 {n_pool}, 이미공백 {n_already}, 스킵 {n_skip}")

# ---- 검증 ----
an = np.frombuffer(bytes(data), dtype=np.uint8); ao = np.frombuffer(orig, dtype=np.uint8)
diff = np.nonzero(ao != an)[0]
in_tx = int(((diff >= tx_fo) & (diff < tx_fo + tx_sz)).sum())
in_hdr = int((diff < 0x100).sum())
print(f"원본 대비 변경 {len(diff):,}B: .text={in_tx} 헤더={in_hdr} (0이어야 함)")
assert in_tx == 0 and in_hdr == 0 and len(data) == len(orig)
open('inject_out/main-safe9', 'wb').write(data)
print("저장 inject_out/main-safe9")
