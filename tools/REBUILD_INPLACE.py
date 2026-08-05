# -*- coding: utf-8 -*-
"""main-clean8 → main-safe20: 접합부 정비를 '문자열 제자리 편집'으로만 재적용.
⚠재배치 테이블 [DYN_LO,DYN_HI]는 절대 쓰지 않음(레코드=상대재배치 엔트리라 손상=부팅크래시).
문자열은 동적영역 밖(>DYN_HI)에 있으므로 in-place 편집만으로 안전.
전략:
 A) 루비 읽기 제거: 문자열이 '단어／かな' 패턴이면 '단어'로 단축(공유 안전=읽기는 원래 안보여야 함)
 B) 문장경계 공백: 재배치를 순회하며 addend가 문자열을 가리키고, 그 문자열이 종결부호로 끝나고
    다음 addend 문자열이 산문 시작이면, 앞 문자열에 후행 공백(제자리 슬랙)
 C) 접합 공백: _junctions_v4의 recA(미정렬 addend 위치) 대신, 재배치 순회로 대체
검증: [DYN_LO,DYN_HI] 무변경(=clean8과 동일)."""
import sys, os, struct, re, json
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

orig = open(r'!exefs-작업/main-원본', 'rb').read()
data = bytearray(open('inject_out/main-clean8', 'rb').read())
tx_fo, tx_mo, tx_sz = struct.unpack_from('<III', orig, 0x10)
ro_fo, ro_mo, ro_sz = struct.unpack_from('<III', orig, 0x20)
ro_lo, ro_hi = ro_mo, ro_mo + ro_sz
DYN_LO, DYN_HI = 0x2aafb79, 0x3d2551d
def off_of(va): return ro_fo + (va - ro_mo)
def in_str_region(off): return DYN_HI <= off < ro_fo + ro_sz

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

# ---- DT_RELA 상대재배치 순회: addend(=문자열 VA) 시퀀스 ----
# MOD0 dynamic 파싱
mod0 = struct.unpack_from('<I', orig, tx_fo+4)[0]
def fo(va):
    if ro_mo <= va < ro_mo+ro_sz: return ro_fo+(va-ro_mo)
    return None
dyn_va = mod0 + struct.unpack_from('<i', orig, fo(ro_mo) if False else (tx_fo+4))[0]  # placeholder
# 간단히: DT_RELA/RELASZ/RELAENT/RELACOUNT 알려진 값 사용(이 게임 실측)
RELA_VA = 0x2ab0058; RELAENT = 0x18; RELACOUNT = 0xc36e2
rela_fo = off_of(RELA_VA)
# 각 엔트리 addend @ +16
records = []   # (addend_file_off, string_va)
for k in range(RELACOUNT):
    ent = rela_fo + k*RELAENT
    r_offset, r_info, r_addend = struct.unpack_from('<QQQ', data, ent)
    if r_info == 0x403 and ro_mo <= r_addend < ro_mo+ro_sz:   # RELATIVE, addend=rodata VA
        records.append((ent+16, r_addend))
print(f"상대재배치(문자열 addend): {len(records):,}")

def read_str(va):
    o = off_of(va)
    if not in_str_region(o): return None, None, 0
    e = data.find(b'\x00', o)
    if e <= o: return '', o, 0
    T = 0; k = e
    while k < len(data) and data[k] == 0: T += 1; k += 1
    return dec(bytes(data[o:e])), o, (e - o) + (T - 1 if T > 0 else 0)
def write_inplace(o, budget, ko):
    """내부 공백 제거 없이 제자리 기록. 예산 초과면 UTF-8 안전 절단만."""
    nb = enc(ko)
    if len(nb) > budget:
        nb = nb[:budget]
        while nb:
            try: nb.decode('utf-8'); break
            except UnicodeDecodeError: nb = nb[:-1]
    region = budget + 1
    data[o:o+len(nb)] = nb
    data[o+len(nb):o+region] = b'\x00' * (region - len(nb))

def hira(c): return '぀' <= c <= 'ゟ'
def kanji(c): return '一' <= c <= '鿿' or c == '々'
def kata(c): return '゠' <= c <= 'ヿ' or c == 'ー'

# 원본 문자열(일본어) 판별용: 같은 addend의 원본 문자열
def read_orig_str(va):
    o = off_of(va)
    if o is None: return None
    e = orig.find(b'\x00', o)
    try: return orig[o:e].decode('utf-8')
    except UnicodeDecodeError: return None

# ---- A) 루비 읽기 제거 ----
ruby_pat = re.compile(r'^[^／]{1,12}／[぀-ゟー]{1,14}$')
n_ruby = 0
seen = set()
for ent, va in records:
    if va in seen: continue
    seen.add(va)
    ojp = read_orig_str(va)
    if not ojp or '／' not in ojp or not ruby_pat.match(ojp): continue
    ko, o, budget = read_str(va)
    if ko is None: continue
    if '／' in ko:
        base = ko.split('／', 1)[0]
        if base:
            write_inplace(o, budget, base); n_ruby += 1
print(f"A) 루비 읽기 제거: {n_ruby}")

# ---- B) 문장경계 + 접합 공백 (재배치 순서 = 표시 순서 가정) ----
END1 = set('はがをにへとのもやで、')
END2 = ('から', 'より', 'まで', 'ずに', 'たり', 'ても', 'では', 'には', 'とは', 'など', 'ように', 'という')
def connective(s): return s and (s[-1] in END1 or any(s.endswith(e) for e in END2))
n_sent = n_junc = 0
seq = [(va, read_orig_str(va)) for ent, va in records]
for i in range(len(seq) - 1):
    va, jp = seq[i]; vb, jpb = seq[i+1]
    if not jp or not jpb or len(jp) < 3: continue
    add = False
    # 문장경계
    if jp[-1] in '。！？' and len(jpb) >= 4 and (any(hira(c) for c in jpb) or any(kanji(c) for c in jpb)):
        add = True; kind = 's'
    # 연결형→명사 접합
    elif connective(jp) and not jp[-1] in '。！？」）' and (kanji(jpb[0]) or kata(jpb[0])):
        add = True; kind = 'j'
    if not add: continue
    ko, o, budget = read_str(va)
    if ko is None or not ko or ko.endswith((' ', '　', '(', '「', '（', '[')): continue
    if not any('가' <= c <= '힣' for c in ko): continue
    if kind == 's' and not ko.endswith(('.', '!', '?', '…', '。')): continue
    nb = enc(ko + ' ')
    if len(nb) > budget + 1: continue        # 슬랙 없으면 스킵(제자리 원칙, 재배치 안 씀)
    write_inplace(o, budget, ko + ' ')
    if kind == 's': n_sent += 1
    else: n_junc += 1
print(f"B) 문장경계 공백 {n_sent}, 접합 공백 {n_junc}")

# ---- 검증: 동적영역 무변경 ----
an = np.frombuffer(bytes(data), dtype=np.uint8)
c8 = np.frombuffer(open('inject_out/main-clean8', 'rb').read(), dtype=np.uint8)
ao = np.frombuffer(orig, dtype=np.uint8)
dyn_chg = int((c8[DYN_LO:DYN_HI] != an[DYN_LO:DYN_HI]).sum())
diff = np.nonzero(ao != an)[0]
in_tx = int(((diff >= tx_fo) & (diff < tx_fo + tx_sz)).sum())
in_hdr = int((diff < 0x100).sum())
print(f"동적영역(재배치) 변경: {dyn_chg} (0이어야=부팅안전)")
print(f".text {in_tx} 헤더 {in_hdr}")
assert dyn_chg == 0 and in_tx == 0 and in_hdr == 0 and len(data) == len(orig)
open('inject_out/main-safe20', 'wb').write(bytes(data))
print("저장 inject_out/main-safe20 (부팅=clean8과 동일 로더경로 + 제자리 접합부 공백)")
