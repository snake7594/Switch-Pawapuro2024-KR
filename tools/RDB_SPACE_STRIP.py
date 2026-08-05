# -*- coding: utf-8 -*-
"""RDB 메뉴 라벨 공백 제거: 주입된(diff) 세그 중 라벨성 문자열의 공백 제거(표시폭 잘림 대응).
조건: 원본 jp에 공백 없음(반각·전각) & jp에 문장부호(。！？…、) 없음 & jp<=16자
      & ko(디코드)에 구두점(.,!?…~) 없음 & \n/%지정자/<태그> 없음 & 공백 포함
동작: ko의 반각·전각 공백 전부 제거 → 제자리 재기록(항상 더 짧음)"""
import sys, os, json, zlib, struct, time, re
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib
from rdblib import align_up, file_key, crypt_fast, SECTOR, locate
import numpy as np

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()
TSVR = {v: k for k, v in TSV.items()}
def dec_ko(s): return ''.join(TSVR.get(c, c) for c in s)
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')

JP_PUNCT = set('。！？…、,.!?~～')
KO_PUNCT = set('.,!?…~～、。')
SPEC = re.compile(r'%[-+ #0-9.]*[sdcfuxXeg]|<[^<>\n]{1,24}>')

def label_fixable(jp, ko):
    if ' ' in jp or '　' in jp: return None
    if len(jp) > 16 or not jp: return None
    if any(c in JP_PUNCT for c in jp): return None
    if '\n' in jp or '\n' in ko: return None
    if SPEC.search(jp) or SPEC.search(ko): return None
    if ' ' not in ko and '　' not in ko: return None
    if any(c in KO_PUNCT for c in ko): return None
    if not any('가' <= c <= '힣' for c in ko): return None
    return ko.replace(' ', '').replace('　', '')

DEP = rdblib.RDB('repack_out', writable=True)
ORG = rdblib.RDB('.')
laid = {"RES00.RDB": [], "RES10.RDB": []}
for t in DEP.table:
    loc = locate(t["stored"], t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
fsize = {n: os.path.getsize(os.path.join('repack_out', n)) for n in DEP.f}
import bisect
def gap_to_next(rdb, local):
    arr = laid[rdb]
    j = bisect.bisect_right(arr, local)
    nxt = arr[j] if j < len(arr) else fsize[rdb]
    return nxt - local
cursor = {n: align_up(fsize[n], SECTOR) for n in DEP.f}
stats = dict(slots=0, strip=0)
samples = []
t0 = time.time(); n = 0
for name, ent in DEP.idx.items():
    if ent['flag'] not in (0, 0x20) or name not in ORG.idx: continue
    n += 1
    try:
        db = DEP.read_body(name); ob = ORG.read_body(name)
    except Exception: continue
    if db is None or ob is None or db == ob or len(db) != len(ob): continue
    buf = bytearray(db)
    a = np.frombuffer(bytes(db), dtype=np.uint8); b = np.frombuffer(ob, dtype=np.uint8)
    diff = np.nonzero(a != b)[0]
    if len(diff) == 0: continue
    changed = 0
    handled = set()
    for x in diff:
        x = int(x)
        st = x
        while st > 0 and ob[st-1] != 0: st -= 1
        if st in handled: continue
        handled.add(st)
        oe = ob.find(b'\x00', st)
        if oe < 0: continue
        ce = bytes(buf).find(b'\x00', st)
        if ce < 0 or ce == st: continue
        try:
            jp = ob[st:oe].decode('utf-8')
            cur = bytes(buf[st:ce]).decode('utf-8')
        except UnicodeDecodeError: continue
        ko = dec_ko(cur)
        new = label_fixable(jp, ko)
        if new is None or new == ko: continue
        nb = enc(new)
        T = 0; k2 = oe
        while k2 < len(ob) and ob[k2] == 0: T += 1; k2 += 1
        region_end = oe + T
        if st + len(nb) >= region_end: continue
        buf[st:st+len(nb)] = nb
        buf[st+len(nb):region_end] = b'\x00' * (region_end - st - len(nb))
        changed += 1
        if len(samples) < 10: samples.append(f'{name}: {ko!r}→{new!r}')
    if not changed: continue
    stats['strip'] += changed; stats['slots'] += 1
    loc = locate(ent["stored"], ent["flag"])
    rdbn, local, is10 = loc
    key = file_key(name); f = DEP.f[rdbn]
    f.seek(local); hdr = bytearray(crypt_fast(f.read(32), key))
    if ent["flag"] == 0x20:
        comp = zlib.compress(bytes(buf), 9)
        struct.pack_into("<I", hdr, 0x18, len(comp))
        nd = align_up(len(buf), 4)
    else:
        comp = bytes(buf)
        nd = align_up(32 + len(buf), 4)
        struct.pack_into("<I", hdr, 0x18, nd)
    need = align_up(32 + len(comp), 4)
    if need <= gap_to_next(rdbn, local):
        struct.pack_into("<I", hdr, 0x1C, local // SECTOR)
        blob = bytearray(need); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(local); f.write(crypt_fast(bytes(blob), key))
        ns = ent["stored"]
    else:
        nl = cursor[rdbn]
        ns, sect = (nl // SECTOR + (0x1000000 if is10 else 0), nl // SECTOR)
        struct.pack_into("<I", hdr, 0x1C, sect)
        phys = align_up(max(nd, 32 + len(comp)), SECTOR)
        blob = bytearray(phys); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(nl); f.write(crypt_fast(bytes(blob), key))
        cursor[rdbn] = nl + phys; fsize[rdbn] = max(fsize[rdbn], cursor[rdbn])
    struct.pack_into("<I", DEP.dec, ent["rec_off"], ns)
    struct.pack_into("<I", DEP.dec, ent["rec_off"]+4, nd)
    ent["stored"] = ns; ent["DEC_SIZE"] = nd
    if n % 3000 == 0: print(f'  {n} ({time.time()-t0:.0f}s)', flush=True)
enc_rdi = crypt_fast(bytes(DEP.dec), rdblib.RDI_KEY)
open(os.path.join('repack_out', 'RES00.RDI'), 'wb').write(enc_rdi)
DEP.close(); ORG.close()
print(f"완료 {time.time()-t0:.0f}s: {stats}")
print(*samples, sep='\n')
