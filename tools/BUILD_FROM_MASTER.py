# -*- coding: utf-8 -*-
"""번역_마스터.json 하나로 exe 전체 재빌드(완전 단일 소스, 무확장).

1단계: main-safe28 + master['exe'] 원본영역 in-place 주입.
2단계(기본, --no-mylife로 끔): 마이라이프 완성문장(master['exe_ext'])을
  '슬롯 꼬리 풀'에 수납하고 RELA addend 리다이렉트.
  - 풀 = 번역 슬롯의 [kr_end+1, jp_end) — 원래 일본어 본문이던 바이트만.
    ⚠후행 NUL런(T)은 제외: 인접 바이너리 테이블의 0-프리픽스일 수 있음(적대검증 실증).
    ⚠죽은조각(리다이렉트로 RELA 참조 전멸) 재사용도 폐기: 코드가 ADRP+ADD 즉치로
      직접 참조하는 UI 문자열(セーブ확인창·図鑑No 등 16+)이 오판됨(적대검증 실증).
      리다이렉트는 하되 조각 바이트는 그대로 보존.
  - 보호셋 = 원본 RELA(전 타입)+JMPREL+SYMTAB + safe28 RELA(잔존 리다이렉트 반영)
    + .text ADRP+ADD/LDST 코드 즉치 타깃(과수집=안전). 참조가 걸리면 꼬리 절단.
  - 대형 문장은 ents 수만큼 분할 배치(ents[0..k-1]→파트, 나머지→빈문자열).
    게임이 ents 순서로 이어붙여 렌더하므로 결과 동일(v1.2 검증).
  ⚠EXPAND(세그먼트 재배치)는 폐기: 게임이 모듈상대 오프셋을 코드 즉치/직렬화 데이터로
    계산해 data를 옮기면 스테일 참조 발생(28일차 크래시 실증, 정적 전수 갱신 불가).
3단계: 무결성 검증(문장 체인 디코드 일치, 변경바이트=할당∪addend 필드만,
  전 보호셋 참조 위치 ∩ 할당 구간 = ∅).

산출: inject_out/main-built. 결정적(동일 master → 동일 md5)."""
import sys, os, json, struct, hashlib, bisect
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
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
DYN_HI = 0x3d2551d
MYLIFE = '--no-mylife' not in sys.argv

orig = open('main', 'rb').read()
def u32(o): return struct.unpack_from('<I', orig, o)[0]
TEXT_FO, TEXT_MO, TEXT_SZ = u32(0x10), u32(0x14), u32(0x18)
ROD_FO, ROD_MO, ROD_SZ = u32(0x20), u32(0x24), u32(0x28)
DATA_FO, DATA_MO, DATA_SZ = u32(0x30), u32(0x34), u32(0x38)
RO_DELTA = ROD_MO - ROD_FO
STR_END_FO = ROD_FO + ROD_SZ          # 문자열영역 상한(파일)
def va2fo(va):
    if TEXT_MO <= va < TEXT_MO+TEXT_SZ: return va-TEXT_MO+TEXT_FO
    if ROD_MO <= va < ROD_MO+ROD_SZ: return va-ROD_MO+ROD_FO
    if DATA_MO <= va < DATA_MO+DATA_SZ: return va-DATA_MO+DATA_FO
    return None

# ================= 1단계: 원본영역 주입 =================
buf = bytearray(open('inject_out/main-safe28', 'rb').read())
es = dict(inj=0, skip=0)
slot_geo = {}   # off → (jp_len, T, kr_len)
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
base28 = np.frombuffer(open('inject_out/main-safe28', 'rb').read(), dtype=np.uint8)
assert (np.frombuffer(bytes(buf), dtype=np.uint8)[:DYN_HI] == base28[:DYN_HI]).all(), "1단계 동적영역 변경!"
print(f"1) 원본영역 주입 {es}")
stage1 = bytes(buf)

if not MYLIFE or not master.get('exe_ext'):
    open('inject_out/main-built', 'wb').write(bytes(buf))
    print(f"→ inject_out/main-built (마이라이프 문장 없음)  md5 {hashlib.md5(bytes(buf)).hexdigest()}")
    sys.exit(0)

# ================= 2단계: 보호셋 + 풀 구축 =================
MOD0_FO = TEXT_FO + u32(TEXT_FO+4)
DYN_FO = va2fo((MOD0_FO-TEXT_FO+TEXT_MO) + struct.unpack_from('<i', orig, MOD0_FO+4)[0])
DYN = {}
o = DYN_FO
while True:
    t, v = struct.unpack_from('<QQ', orig, o)
    if t == 0: break
    DYN.setdefault(t, v); o += 16
from collections import defaultdict
RELA_FO = va2fo(DYN[7]); RELA_CNT = DYN[8]//24
arr = np.frombuffer(orig[RELA_FO:RELA_FO+RELA_CNT*24], dtype='<u8').reshape(-1, 3)
refs = [arr[:, 2].astype(np.int64)]                               # 원본 RELA 전 타입 addend
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
# safe28(현 베이스)의 RELA addend — 과거 리다이렉트 잔존 참조 반영
s28 = np.frombuffer(stage1[RELA_FO:RELA_FO+RELA_CNT*24], dtype='<u8').reshape(-1, 3)
refs.append(s28[s28[:, 1] == 0x403][:, 2].astype(np.int64))
# .text 코드 즉치 타깃: ADRP + (ADD imm | LDR/STR unsigned imm) 페어(과수집=안전)
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
        if (wj & 0xFFC00000) in (0x91000000, 0x91400000) and ((wj >> 5) & 0x1f) == rd:   # ADD imm
            imm = (wj >> 10) & 0xfff
            if (wj & 0xFFC00000) == 0x91400000: imm <<= 12
            code_tgts.append(page + imm)
        elif (wj & 0x3B000000) == 0x39000000 and ((wj >> 5) & 0x1f) == rd:               # LDR/STR uimm
            size = (wj >> 30) & 3
            code_tgts.append(page + (((wj >> 10) & 0xfff) << size))
refs.append(np.array(code_tgts, dtype=np.int64))
allref = np.concatenate(refs)
inreg = allref[(allref >= STR_LO_VA) & (allref < ROD_MO + ROD_SZ)]
ref_fo = np.unique(inreg - RO_DELTA)   # 문자열영역 참조 파일오프셋(정렬·중복제거)
print(f"2) 보호셋: RELA(원본+safe28)+JMPREL+SYMTAB+코드즉치 {len(code_tgts):,} → 문자열영역 참조 {len(ref_fo):,}곳")
def first_ref_in(lo, hi):
    j = np.searchsorted(ref_fo, lo, side='left')
    return int(ref_fo[j]) if j < len(ref_fo) and ref_fo[j] < hi else None

# 활성 ents 검증 + 멀티필드(비연속 ents) 제외
# ⚠ents가 RELA에서 연속(24 stride)이 아니면 = 사이에 구분 슬롯 존재 = 하나의 대사가 아니라
#   별개 UI 필드(제목/프롬프트/내레이션)들이다. 이어붙이면 필드가 깨지므로 리다이렉트 제외
#   → safe28의 필드별 개별 번역 정렬을 그대로 보존(적대검증 실증).
ext = []
multifield = 0
seen_ent = set()
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

# 풀: 슬롯 꼬리 [kr_end+1, jp_end). 원래 일본어 본문이던 바이트만(NUL런 완전 제외:
# 인접 바이너리 테이블 0-프리픽스 보호). 구간 내 보호셋 참조(코드즉치 포함) 앞에서 절단.
tails = []
for off, (jl, T, kl) in slot_geo.items():
    jp_end = off + jl
    lo = off + kl + 1
    if lo >= jp_end: continue
    p = first_ref_in(off+1, jp_end)
    if p is not None and p <= lo: continue
    hi = jp_end if p is None else min(jp_end, p)
    if hi - lo >= 8: tails.append((lo, hi))

# 죽은조각 풀: 리다이렉트로 '모든' 참조가 사라지는 조각 슬롯(큰 청크 공급원).
# 삼중 보호: (1) 그 조각을 가리키는 전 RELA(0x403+비상대) 참조가 모두 ours,
#           (2) 조각 시작 fo가 보호셋(코드즉치·safe28·SYMTAB…) 어디에도 없음,
#           (3) 구간 내 보호셋 참조로 절단. NUL런 제외(문자열 끝까지만).
ref_fo_set = set(int(x) for x in ref_fo)
frag_vas = set()
for ep in ours: frag_vas.add(struct.unpack_from('<Q', orig, ep+16)[0])
ra_all = arr[:, 2]
ours_set = set(ours)
sel = np.isin(ra_all, np.array(sorted(frag_vas), dtype=np.uint64))   # 전 타입(0x403 포함)
ref_ents = defaultdict(list)
for k in np.nonzero(sel)[0].tolist():
    ref_ents[int(ra_all[k])].append(RELA_FO + k*24)
dead = []
tail_lo = {lo for lo, _ in tails}
for F in sorted(frag_vas):
    ents_f = ref_ents.get(F, [])
    if not ents_f or any(e not in ours_set for e in ents_f): continue   # 외부 RELA 참조 생존
    fo = va2fo(F)
    if fo is None or fo <= DYN_HI: continue
    if fo in ref_fo_set: continue                                       # 코드즉치/safe28 등 참조
    e = orig.find(b'\x00', fo)                                          # 문자열 끝(NUL런 제외)
    if e < 0 or e <= fo: continue
    p = first_ref_in(fo+1, e)
    hi = e if p is None else min(e, p)
    if hi - fo >= 8: dead.append((fo, hi))
print(f"   죽은조각 풀(삼중보호): {len(dead):,}청크 {sum(h-l for l,h in dead):,}B")

pool = sorted(tails + dead)
for i in range(1, len(pool)):
    assert pool[i][0] >= pool[i-1][1], "풀 구간 겹침!"
for l, h in pool:
    assert DYN_HI < l and h <= STR_END_FO, "풀이 문자열영역 밖!"
pool_total = sum(h-l for l, h in pool)
print(f"   풀(꼬리, NUL런 제외): {len(pool):,}청크 {pool_total:,}B")

# ================= 2단계: 수납 + 리다이렉트 =================
from collections import defaultdict
# 할당기: (남은크기, 시작off) 정렬 리스트에서 best-fit. 할당 구간 기록.
free = sorted([h-l, l] for l, h in pool)   # [size, off]
allocated = []
def alloc(n):
    keys = [f[0] for f in free]
    j = bisect.bisect_left(keys, n)
    if j >= len(free): return None
    size, off = free.pop(j)
    if size - n > 0: bisect.insort(free, [size - n, off + n])
    allocated.append((off, off + n))
    buf[off:off+n] = b'\x00' * n           # 죽은조각 잔재 제거(꼬리는 이미 NUL)
    return off
def utf8_floor(b, n):
    while n > 0 and n < len(b) and (b[n] & 0xC0) == 0x80: n -= 1
    return n

empty_off = alloc(1)                      # 빈문자열(0 바이트)
EMPTY_VA = empty_off + RO_DELTA

bysent = defaultdict(list)                # enc → [entries]
for x in ext: bysent[enc(x['ko'])].append(x)
def hardness(b):                           # 파트당 필요 바이트(제약 심한 순)
    k = min(len(x['ents']) for x in bysent[b])
    return -(-(len(b)+1) // k)
sents = sorted(bysent.keys(), key=lambda b: (-hardness(b), -len(b), b))
placed_va = {}                            # enc → [파트VA...] | None=수납불가(리다이렉트 포기)
st = dict(whole=0, split=0, parts=0, skip=0)
for sb in sents:
    budget = min(len(x['ents']) for x in bysent[sb])
    off = alloc(len(sb) + 1)
    if off is not None:
        buf[off:off+len(sb)] = sb; buf[off+len(sb)] = 0
        placed_va[sb] = [off + RO_DELTA]; st['whole'] += 1
        continue
    # 분할: 파트수 ≤ budget. 매 파트를 '가장 큰 가용 청크'로 채움(비대칭 패킹) →
    # 큰 청크를 문장당 최소 개수만 소비, 파편화 풀에서 수납률 최대.
    parts = []; my_allocs = []; rem = sb
    while rem:
        if len(parts) == budget: break
        maxc = free[-1][0] if free else 0           # 최대 가용 청크
        if maxc < 2: break
        take = utf8_floor(rem, min(len(rem), maxc - 1))
        if take == 0: break
        off = alloc(take + 1)                        # best-fit(take+1 이상 최소) = 대개 maxc
        if off is None: break
        buf[off:off+take] = rem[:take]; buf[off+take] = 0
        parts.append(off + RO_DELTA); my_allocs.append((off, take+1)); rem = rem[take:]
    if rem:   # 수납 불가 → 롤백 후 스킵(원본 조각 표시 유지)
        for o2, n in my_allocs:
            buf[o2:o2+n] = b'\x00' * n
            allocated.remove((o2, o2+n))
            bisect.insort(free, [n, o2])
        placed_va[sb] = None; st['skip'] += 1
        continue
    placed_va[sb] = parts; st['split'] += 1; st['parts'] += len(parts)

# 리다이렉트: ents[0..k-1]→파트, 나머지→빈문자열. 수납불가 문장은 손대지 않음.
red = dict(redir=0, empt=0)
for x in ext:
    vas = placed_va[enc(x['ko'])]
    if vas is None: continue
    for i, ep in enumerate(x['ents']):
        va = vas[i] if i < len(vas) else EMPTY_VA
        struct.pack_into('<Q', buf, ep+16, va)
        red['redir' if i < len(vas) else 'empt'] += 1
print(f"3) 수납: 통짜 {st['whole']:,} + 분할 {st['split']:,}({st['parts']}파트) + 스킵 {st['skip']:,} / 리다이렉트 {red}")
# 스킵 목록(축약 대상) 저장
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
    if placed_va[enc(x['ko'])] is None: continue   # 스킵분: 원본 조각 그대로
    checked += 1
    got = b''
    for ep in x['ents']:
        got += read_str(struct.unpack_from('<Q', mb, ep+16)[0])
    if dec(got) != x['ko']: bad += 1
assert bad == 0, f"문장 체인 불일치 {bad}"
# 변경 바이트 규율: stage1 대비 diff ⊆ 할당 구간 ∪ ents addend(8B)
a = np.frombuffer(mb, dtype=np.uint8); b1 = np.frombuffer(stage1, dtype=np.uint8)
diff = np.nonzero(a != b1)[0]
ok_mask = np.zeros(len(mb), dtype=bool)
for l, h in allocated: ok_mask[l:h] = True
for ep in ours: ok_mask[ep+16:ep+24] = True
viol = diff[~ok_mask[diff]]
assert len(viol) == 0, f"규율 위반 바이트 {len(viol)}: {[hex(int(v)) for v in viol[:5]]}"
# 보호셋 참조 위치가 할당 구간과 겹치지 않는가(최후 안전망)
alloc_mask = np.zeros(len(mb), dtype=bool)
for l, h in allocated: alloc_mask[l:h] = True
hit = ref_fo[(ref_fo < len(mb))]
hit = hit[alloc_mask[hit]]
assert len(hit) == 0, f"보호셋 참조가 할당 구간 침범 {len(hit)}: {[hex(int(v)) for v in hit[:5]]}"
# 헤더/코드/데이터 불변
assert (a[:0x100] == b1[:0x100]).all() and (a[TEXT_FO:TEXT_FO+TEXT_SZ] == b1[TEXT_FO:TEXT_FO+TEXT_SZ]).all()
assert (a[DATA_FO:] == b1[DATA_FO:]).all()
alloc_total = sum(h-l for l, h in allocated)
print(f"4) 검증: 문장체인 {checked:,}/{checked:,} 일치(스킵 {st['skip']}), diff {len(diff):,}B 규율 내, "
      f"보호셋 침범 0, 할당 {alloc_total:,}B, text/data 불변")

open('inject_out/main-built', 'wb').write(mb)
print(f"→ inject_out/main-built  md5 {hashlib.md5(mb).hexdigest()}  (무확장, 크기 {len(mb):,})")
