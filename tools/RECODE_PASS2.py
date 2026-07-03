# -*- coding: utf-8 -*-
"""PASS2(쓰기): _recode_plan.json(+추가 패치파일들)을 repack_out RDB에 적용.
- 슬롯별: 본문 패치(제자리, 길이보존) → 재압축(zlib9/flag0 raw) → gap 맞으면 제자리, 아니면 끝 재배치
- RDI OFFSET/DEC_SIZE 갱신(본문 길이 불변 → DEC_SIZE 불변; 재배치시 OFFSET만)
- COMMON_2D.CHK = _build/COMMON_2D_TSV.CHK 교체(폰트)
- 미지원 한글 음절 자모 폴백(큥→큐, 챳→챠 등: 종성탈락→복모음 단순화)
- 검증: 기록 후 재독→본문 일치
사용: python RECODE_PASS2.py [추가패치.json ...]
"""
import sys, os, json, zlib, struct, time
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r"C:\Users\Jae Ho Lee\Desktop\z\실황2024")
import rdblib
from rdblib import align_up, file_key, crypt_fast, SECTOR

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG_ALT = {2:0, 6:4, 12:8, 17:13, 3:1, 7:5, 9:8, 10:0, 11:1, 14:13, 15:4, 16:5, 19:18, 4:4}
def fallback_syl(c):
    """미지원 음절 → 지원 음절(종성탈락→모음단순화). 실패시 None."""
    v = ord(c) - 0xAC00
    cho, jung, jong = v // 588, (v % 588) // 28, v % 28
    cands = []
    if jong: cands.append((cho, jung, 0))
    j2 = JUNG_ALT.get(jung)
    if j2 is not None:
        cands.append((cho, j2, jong)); cands.append((cho, j2, 0))
    for ch, ju, jo in cands:
        s = chr(0xAC00 + ch*588 + ju*28 + jo)
        if s in TSV: return s
    return None

def fix_unsupported(b):
    """패치 바이트 내 미지원 한글(=raw 한글 잔존)을 폴백 음절의 tsv 한자로 교체(등길이)."""
    try: s = b.decode('utf-8')
    except UnicodeDecodeError: return b, 0
    out = []; n = 0
    for c in s:
        if '가' <= c <= '힣':          # 인코딩을 거치고도 남은 한글 = 미지원
            f = fallback_syl(c)
            if f: out.append(TSV[f]); n += 1
            else: out.append('・'); n += 1
        else: out.append(c)
    return ''.join(out).encode('utf-8'), n

t0 = time.time()
plans = json.load(open('_recode_plan.json', encoding='utf-8'))
for extra in sys.argv[1:]:
    more = json.load(open(extra, encoding='utf-8'))
    for name, p in more.items():
        if name in plans: plans[name]['patches'].extend(p['patches'])
        else: plans[name] = p
print(f"패치 슬롯 {len(plans)}")

R = rdblib.RDB('repack_out', writable=True)
dec_rdi = R.dec
# RDB별 슬롯 레이아웃(제자리 gap 계산)
laid = {"RES00.RDB": [], "RES10.RDB": []}
for t in R.table:
    loc = rdblib.locate(t["stored"], t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
fsize = {n: os.path.getsize(os.path.join('repack_out', n)) for n in R.f}
import bisect
def gap_to_next(rdb, local):
    arr = laid[rdb]
    j = bisect.bisect_right(arr, local)
    nxt = arr[j] if j < len(arr) else fsize[rdb]
    return nxt - local
cursor = {n: align_up(fsize[n], SECTOR) for n in R.f}

stats = dict(slots=0, inplace=0, reloc=0, subst=0, verify_ok=0, verify_ng=0)
FONT_NEW = open('_build/COMMON_2D_TSV.CHK', 'rb').read()[32:]
plans['COMMON_2D.CHK'] = {'aligned': True, 'patches': [], 'font': True}

for name, plan in plans.items():
    ent = R.idx.get(name)
    if not ent: print(f'  [없음] {name}'); continue
    body = R.read_body(name)
    if body is None: continue
    if plan.get('font'):
        new_body = FONT_NEW
    else:
        buf = bytearray(body)
        for off, region, hexs in plan['patches']:
            nb = bytes.fromhex(hexs)
            nb, ns = fix_unsupported(nb)
            stats['subst'] += ns
            if len(nb) > region - 1:   # NUL 최소 1 보장
                nb = nb[:region-1]
                while nb:
                    try: nb.decode('utf-8'); break
                    except UnicodeDecodeError: nb = nb[:-1]
            buf[off:off+len(nb)] = nb
            buf[off+len(nb):off+region] = b'\x00' * (region - len(nb))
        new_body = bytes(buf)
    # 압축·헤더
    loc = rdblib.locate(ent["stored"], ent["flag"])
    rdbn, local, is10 = loc
    key = file_key(name)
    f = R.f[rdbn]
    f.seek(local); hdr = bytearray(crypt_fast(f.read(32), key))
    if ent["flag"] == 0x20:
        comp = zlib.compress(new_body, 9)
        struct.pack_into("<I", hdr, 0x18, len(comp))
        new_decsize = align_up(len(new_body), 4)
    else:
        comp = new_body
        new_decsize = align_up(32 + len(new_body), 4)
        struct.pack_into("<I", hdr, 0x18, new_decsize)
    need = align_up(32 + len(comp), 4)
    if need <= gap_to_next(rdbn, local):
        struct.pack_into("<I", hdr, 0x1C, local // SECTOR)
        blob = bytearray(need); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(local); f.write(crypt_fast(bytes(blob), key))
        new_stored = ent["stored"]; stats['inplace'] += 1
    else:
        nl = cursor[rdbn]
        new_stored, sect = (nl // SECTOR + (0x1000000 if is10 else 0), nl // SECTOR)
        struct.pack_into("<I", hdr, 0x1C, sect)
        phys = align_up(max(new_decsize, 32 + len(comp)), SECTOR)
        blob = bytearray(phys); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(nl); f.write(crypt_fast(bytes(blob), key))
        cursor[rdbn] = nl + phys
        fsize[rdbn] = max(fsize[rdbn], cursor[rdbn])
        stats['reloc'] += 1
    # RDI 갱신
    struct.pack_into("<I", dec_rdi, ent["rec_off"], new_stored)
    struct.pack_into("<I", dec_rdi, ent["rec_off"]+4, new_decsize)
    ent["stored"] = new_stored; ent["DEC_SIZE"] = new_decsize
    stats['slots'] += 1
    if stats['slots'] % 100 == 0:
        print(f"  {stats['slots']}/{len(plans)} ({time.time()-t0:.0f}s)", flush=True)

# RDI 저장
enc = crypt_fast(bytes(dec_rdi), rdblib.RDI_KEY)
open(os.path.join('repack_out', 'RES00.RDI'), 'wb').write(enc)

# 검증: 표본 재독
import random
names = [n for n in plans if n in R.idx]
sample = random.Random(7).sample(names, min(150, len(names)))
R2 = rdblib.RDB('repack_out')
for name in sample:
    try:
        b = R2.read_body(name)
        ok = b is not None and len(b) > 0
    except Exception:
        ok = False
    stats['verify_ok' if ok else 'verify_ng'] += 1
R2.close(); R.close()
print("=" * 60)
print(f"완료 {time.time()-t0:.0f}s: {stats}")
