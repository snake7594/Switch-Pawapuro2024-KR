# -*- coding: utf-8 -*-
"""번역_마스터.json 하나로 exe 전체 재빌드(무확장) — 버전 비의존판.

BUILD_FROM_MASTER.py 와 동일한 공법이지만 DYN_HI 등 상수를 바이너리에서 유도한다.
  1단계: inject_out/main-base + master['exe'] 원본영역 in-place 주입
  2단계: 마이라이프 완성문장(master['exe_ext'])을 슬롯 꼬리 풀에 수납 + RELA addend 리다이렉트
  3단계: 무결성 검증(문장체인·변경바이트 규율·보호셋 침범 0·text/data/헤더 불변)
산출: inject_out/main-built (결정적)
"""
import sys, os, json, struct, hashlib, bisect
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)
import numpy as np

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv(); TSVR = {v: k for k, v in TSV.items()}
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')
def dec(b):
    try: return ''.join(TSVR.get(c, c) for c in b.decode('utf-8'))
    except UnicodeDecodeError: return None
def fit(nb, region):
    if len(nb) > region - 1:
        nb = nb[:region-1]
        while nb:
            try: nb.decode('utf-8'); break
            except UnicodeDecodeError: nb = nb[:-1]
    return nb

master = json.load(open('번역_마스터.json', encoding='utf-8'))
MYLIFE = '--no-mylife' not in sys.argv
BASE = 'inject_out/main-base'

orig = open('main', 'rb').read()
def u32(o): return struct.unpack_from('<I', orig, o)[0]
TEXT_FO, TEXT_MO, TEXT_SZ = u32(0x10), u32(0x14), u32(0x18)
ROD_FO, ROD_MO, ROD_SZ = u32(0x20), u32(0x24), u32(0x28)
DATA_FO, DATA_MO, DATA_SZ = u32(0x30), u32(0x34), u32(0x38)
RO_DELTA = ROD_MO - ROD_FO
STR_END_FO = ROD_FO + ROD_SZ
def va2fo(va):
    if TEXT_MO <= va < TEXT_MO+TEXT_SZ: return va-TEXT_MO+TEXT_FO
    if ROD_MO <= va < ROD_MO+ROD_SZ: return va-ROD_MO+ROD_FO
    if DATA_MO <= va < DATA_MO+DATA_SZ: return va-DATA_MO+DATA_FO
    return None

MOD0_FO = TEXT_FO + u32(TEXT_FO+4)
DYN_FO = va2fo((MOD0_FO-TEXT_FO+TEXT_MO) + struct.unpack_from('<i', orig, MOD0_FO+4)[0])
DYN = {}
o = DYN_FO
while True:
    t, v = struct.unpack_from('<QQ', orig, o)
    if t == 0: break
    DYN.setdefault(t, v); o += 16
# 동적 구조 영역 상한 = STRTAB 끝 - 1 (이 이하는 절대 손대지 않는다)
DYN_HI = va2fo(DYN[5]) + DYN[10] - 1
print(f"0) DYN_HI=0x{DYN_HI:x} 문자열영역 0x{DYN_HI+1:x}~0x{STR_END_FO:x} 크기 {len(orig):,}")

# ================= 1단계: 원본영역 주입 =================
buf = bytearray(open(BASE, 'rb').read())
assert len(buf) == len(orig), "베이스 크기 불일치"
es = dict(inj=0, skip=0)
slot_geo = {}
for r in master['exe']:
    off, ko = r['off'], r['ko']
    if off <= DYN_HI: es['skip'] += 1; continue
    jpb = r['jp'].encode('utf-8')
    if orig[off:off+len(jpb)] != jpb: es['skip'] += 1; continue
    e = off + len(jpb); T = 0
    while e+T < len(orig) and orig[e+T] == 0: T += 1
    region = len(jpb) + T
    nb = fit(enc(ko), region)
    buf[off:off+len(nb)] = nb
    buf[off+len(nb):off+region] = b'\x00' * (region - len(nb))
    slot_geo[off] = (len(jpb), T, len(nb))
    es['inj'] += 1
base_a = np.frombuffer(open(BASE, 'rb').read(), dtype=np.uint8)
assert (np.frombuffer(bytes(buf), dtype=np.uint8)[:DYN_HI] == base_a[:DYN_HI]).all(), "1단계 동적영역 변경!"
print(f"1) 원본영역 주입 {es}")
stage1 = bytes(buf)

if not MYLIFE or not master.get('exe_ext'):
    open('inject_out/main-built', 'wb').write(bytes(buf))
    print(f"→ inject_out/main-built (마이라이프 문장 없음)  md5 {hashlib.md5(bytes(buf)).hexdigest()}")
    sys.exit(0)

# ================= 2단계: 보호셋 + 풀 =================
RELA_FO = va2fo(DYN[7]); RELA_CNT = DYN[8]//24
arr = np.frombuffer(orig[RELA_FO:RELA_FO+RELA_CNT*24], dtype='<u8').reshape(-1, 3)
refs = [arr[:, 2].astype(np.int64)]
if DYN.get(23):
    jfo = va2fo(DYN[23]); jcnt = DYN.get(2, 0)//24
    jarr = np.frombuffer(orig[jfo:jfo+jcnt*24], dtype='<u8').reshape(-1, 3)
    refs.append(jarr[:, 2].astype(np.int64))
sym_vals = []
if DYN.get(6) and DYN.get(5):
    sfo = va2fo(DYN[6]); nsym = (DYN[5]-DYN[6])//DYN.get(11, 0x18)
    for i in range(nsym):
        sym_vals.append(struct.unpack_from('<Q', orig, sfo+i*DYN.get(11, 0x18)+8)[0])
refs.append(np.array(sym_vals, dtype=np.int64))
# 베이스(풀 리다이렉트 반영)의 RELA addend
s_b = np.frombuffer(stage1[RELA_FO:RELA_FO+RELA_CNT*24], dtype='<u8').reshape(-1, 3)
refs.append(s_b[s_b[:, 1] == 0x403][:, 2].astype(np.int64))
# 베이스 전체의 데이터 포인터(풀 리다이렉트로 생긴 .data 참조 포함)
for seg_fo, seg_sz in ((ROD_FO, ROD_SZ), (DATA_FO, DATA_SZ)):
    n = seg_sz // 8
    w = np.frombuffer(stage1[seg_fo:seg_fo+n*8], dtype='<u8')
    refs.append(w[(w >= ROD_MO) & (w < ROD_MO+ROD_SZ)].astype(np.int64))
# .text 코드 즉치 타깃
text = np.frombuffer(orig[TEXT_FO:TEXT_FO+TEXT_SZ], dtype='<u4')
pc = TEXT_MO + np.arange(len(text), dtype=np.int64)*4
w64 = text.astype(np.int64)
is_adrp = (text & 0x9f000000) == 0x90000000
ai = np.nonzero(is_adrp)[0]
lo21 = ((w64[ai] >> 29) & 3) | (((w64[ai] >> 5) & 0x7ffff) << 2)
lo21 = np.where(lo21 & (1 << 20), lo21 - (1 << 21), lo21)
pages = (pc[ai] & ~0xfff) + lo21*0x1000
code_tgts = []
W = 8
STR_LO_VA = ROD_MO + (DYN_HI - ROD_FO)
cand = np.nonzero((pages >= STR_LO_VA - 0x1000) & (pages < ROD_MO + ROD_SZ))[0]
for k in cand.tolist():
    i0 = ai[k]; rd = int(text[i0]) & 0x1f; page = int(pages[k])
    for j in range(i0+1, min(i0+1+W, len(text))):
        wj = int(text[j])
        if (wj & 0xFFC00000) in (0x91000000, 0x91400000) and ((wj >> 5) & 0x1f) == rd:
            imm = (wj >> 10) & 0xfff
            if (wj & 0xFFC00000) == 0x91400000: imm <<= 12
            code_tgts.append(page + imm)
        elif (wj & 0x3B000000) == 0x39000000 and ((wj >> 5) & 0x1f) == rd:
            size = (wj >> 30) & 3
            code_tgts.append(page + (((wj >> 10) & 0xfff) << size))
refs.append(np.array(code_tgts, dtype=np.int64))
allref = np.concatenate(refs)
inreg = allref[(allref >= STR_LO_VA) & (allref < ROD_MO + ROD_SZ)]
ref_fo = np.unique(inreg - RO_DELTA)
print(f"2) 보호셋: RELA(원본+베이스)+JMPREL+SYMTAB+데이터포인터+코드즉치 {len(code_tgts):,} "
      f"→ 문자열영역 참조 {len(ref_fo):,}곳")
def first_ref_in(lo, hi):
    j = np.searchsorted(ref_fo, lo, side='left')
    return int(ref_fo[j]) if j < len(ref_fo) and ref_fo[j] < hi else None

ext = []; multifield = 0; seen_ent = set()
for x in master['exe_ext']:
    se = sorted(x['ents'])
    if len(se) >= 2 and any(se[i+1]-se[i] != 24 for i in range(len(se)-1)):
        multifield += 1; continue
    ext.append(x)
ours = []
for x in ext:
    for ep in x['ents']:
        assert ep not in seen_ent, f"ent 중복 {hex(ep)}"
        seen_ent.add(ep)
        assert RELA_FO <= ep < RELA_FO+RELA_CNT*24 and (ep-RELA_FO) % 24 == 0, f"ent 비정상 {hex(ep)}"
        ro_, ri_, ra_ = struct.unpack_from('<QQQ', orig, ep)
        assert ri_ == 0x403, f"ent r_info {hex(ri_)}"
        ours.append(ep)
print(f"   멀티필드(비연속 ents) 제외: {multifield} → 완성문장 대상 {len(ext):,}")

tails = []
for off, (jl, T, kl) in slot_geo.items():
    jp_end = off + jl
    lo = off + kl + 1
    if lo >= jp_end: continue
    p = first_ref_in(off+1, jp_end)
    if p is not None and p <= lo: continue
    hi = jp_end if p is None else min(jp_end, p)
    if hi - lo >= 8: tails.append((lo, hi))
pool = sorted(tails)
for i in range(1, len(pool)):
    assert pool[i][0] >= pool[i-1][1], "풀 구간 겹침!"
for l, h in pool:
    assert DYN_HI < l and h <= STR_END_FO, "풀이 문자열영역 밖!"
print(f"   풀(꼬리, NUL런 제외): {len(pool):,}청크 {sum(h-l for l, h in pool):,}B")

# ================= 2단계: 수납 + 리다이렉트 =================
free = sorted([h-l, l] for l, h in pool)
allocated = []
def alloc(n):
    keys = [f[0] for f in free]
    j = bisect.bisect_left(keys, n)
    if j >= len(free): return None
    size, off = free.pop(j)
    if size - n > 0: bisect.insort(free, [size - n, off + n])
    allocated.append((off, off + n))
    buf[off:off+n] = b'\x00' * n
    return off
def utf8_floor(b, n):
    while n > 0 and n < len(b) and (b[n] & 0xC0) == 0x80: n -= 1
    return n

empty_off = alloc(1)
EMPTY_VA = empty_off + RO_DELTA
bysent = defaultdict(list)
for x in ext: bysent[enc(x['ko'])].append(x)
def hardness(b):
    k = min(len(x['ents']) for x in bysent[b])
    return -(-(len(b)+1) // k)
sents = sorted(bysent.keys(), key=lambda b: (-hardness(b), -len(b), b))
placed_va = {}
st = dict(whole=0, split=0, parts=0, skip=0)
for sb in sents:
    budget = min(len(x['ents']) for x in bysent[sb])
    off = alloc(len(sb) + 1)
    if off is not None:
        buf[off:off+len(sb)] = sb; buf[off+len(sb)] = 0
        placed_va[sb] = [off + RO_DELTA]; st['whole'] += 1
        continue
    parts = []; my_allocs = []; rem = sb
    while rem:
        if len(parts) == budget: break
        maxc = free[-1][0] if free else 0
        if maxc < 2: break
        take = utf8_floor(rem, min(len(rem), maxc - 1))
        if take == 0: break
        off = alloc(take + 1)
        if off is None: break
        buf[off:off+take] = rem[:take]; buf[off+take] = 0
        parts.append(off + RO_DELTA); my_allocs.append((off, take+1)); rem = rem[take:]
    if rem:
        for o2, n in my_allocs:
            buf[o2:o2+n] = b'\x00' * n
            allocated.remove((o2, o2+n))
            bisect.insort(free, [n, o2])
        placed_va[sb] = None; st['skip'] += 1
        continue
    placed_va[sb] = parts; st['split'] += 1; st['parts'] += len(parts)

red = dict(redir=0, empt=0)
for x in ext:
    vas = placed_va[enc(x['ko'])]
    if vas is None: continue
    for i, ep in enumerate(x['ents']):
        va = vas[i] if i < len(vas) else EMPTY_VA
        struct.pack_into('<Q', buf, ep+16, va)
        red['redir' if i < len(vas) else 'empt'] += 1
print(f"3) 수납: 통짜 {st['whole']:,} + 분할 {st['split']:,}({st['parts']}파트) + 스킵 {st['skip']:,} / 리다이렉트 {red}")
ko_by_sb = {}
for x in ext: ko_by_sb.setdefault(enc(x['ko']), (x['ko'], x['ents']))
skips = []
for sb in sents:
    if placed_va[sb] is not None: continue
    ko, ents = ko_by_sb[sb]
    skips.append({'ko': ko, 'bytes': len(sb), 'budget': min(len(x['ents']) for x in bysent[sb]), 'ents': ents})
json.dump(skips, open('_ext_skip.json', 'w', encoding='utf-8'), ensure_ascii=False)

# ================= 3단계: 검증 =================
mb = bytes(buf)
def read_str(va):
    fo = va - RO_DELTA
    e = mb.find(b'\x00', fo)
    return mb[fo:e]
bad = 0; checked = 0
for x in ext:
    if placed_va[enc(x['ko'])] is None: continue
    checked += 1
    got = b''
    for ep in x['ents']:
        got += read_str(struct.unpack_from('<Q', mb, ep+16)[0])
    if dec(got) != x['ko']: bad += 1
assert bad == 0, f"문장 체인 불일치 {bad}"
a = np.frombuffer(mb, dtype=np.uint8); b1 = np.frombuffer(stage1, dtype=np.uint8)
diff = np.nonzero(a != b1)[0]
ok_mask = np.zeros(len(mb), dtype=bool)
for l, h in allocated: ok_mask[l:h] = True
for ep in ours: ok_mask[ep+16:ep+24] = True
viol = diff[~ok_mask[diff]]
assert len(viol) == 0, f"규율 위반 바이트 {len(viol)}: {[hex(int(v)) for v in viol[:5]]}"
alloc_mask = np.zeros(len(mb), dtype=bool)
for l, h in allocated: alloc_mask[l:h] = True
hit = ref_fo[(ref_fo < len(mb))]
hit = hit[alloc_mask[hit]]
assert len(hit) == 0, f"보호셋 참조가 할당 구간 침범 {len(hit)}: {[hex(int(v)) for v in hit[:5]]}"
assert (a[:0x100] == b1[:0x100]).all() and (a[TEXT_FO:TEXT_FO+TEXT_SZ] == b1[TEXT_FO:TEXT_FO+TEXT_SZ]).all()
assert (a[DATA_FO:] == b1[DATA_FO:]).all()
print(f"4) 검증: 문장체인 {checked:,}/{checked:,} 일치(스킵 {st['skip']}), diff {len(diff):,}B 규율 내, "
      f"보호셋 침범 0, 할당 {sum(h-l for l, h in allocated):,}B, text/data 불변")
open('inject_out/main-built', 'wb').write(mb)
print(f"→ inject_out/main-built  md5 {hashlib.md5(mb).hexdigest()}  (무확장, 크기 {len(mb):,})")
