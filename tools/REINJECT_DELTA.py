# -*- coding: utf-8 -*-
"""바이너리 컨테이너 과복원 델타 재주입.
- 대상: _bogus_report 파일 중 텍스트파일(REINJECT_TEXT2 완료)·栄冠 파일 제외 전부
- 조건: 현재==원본(복원됨) & 원본 세그가 plausible_jp v2 & 가나 포함 & dict 매칭 → ko 재주입
  (가나 없는 한자-only는 바이너리 오탐 위험 → 원본 유지)"""
import sys, os, json, zlib, struct, time, re
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib
from rdblib import align_up, file_key, crypt_fast, SECTOR, locate
from _plaus import plausible_jp

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')
DICT = json.load(open('_dict_jpko.json', encoding='utf-8'))
rep = json.load(open('_bogus_report.json', encoding='utf-8'))
textpat = re.compile(r'^(SEN_|TEXT_|NAME_DIC|PAWADICT|PEN_|SCS|CHALLENGE|LIVE_STG|ORDER|REC_|CMP_|VERSUS|UTL|ARENA_RANKING)')
EIKAN = lambda n: n.startswith(('HSIM', 'HATK', 'G2D_HATK', 'D2D_HATK'))
targets = [f for f in rep if not textpat.match(f) and not EIKAN(f)]
print(f"델타 재주입 대상 파일 {len(targets)}")

def has_kana(s): return any('぀' <= c <= 'ヿ' for c in s)

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
stats = dict(files=0, inj=0, inplace=0, reloc=0)
t0 = time.time(); nn = 0
samples = []
for fn in targets:
    nn += 1
    ent = DEP.idx.get(fn)
    if not ent or ent['flag'] not in (0, 0x20) or fn not in ORG.idx: continue
    try:
        body = bytearray(DEP.read_body(fn))
        ob = ORG.read_body(fn)
    except Exception: continue
    if ob is None or len(body) != len(ob): continue
    ok = 0
    pos = 0
    while pos < len(ob):
        e = ob.find(b'\x00', pos)
        if e < 0: break
        if 4 <= e - pos <= 300:
            # 현재==원본(복원/미주입) 세그만
            if bytes(body[pos:e]) == ob[pos:e]:
                try: s = ob[pos:e].decode('utf-8')
                except UnicodeDecodeError: s = None
                if s and has_kana(s) and plausible_jp(s):
                    ko = DICT.get(s)
                    if ko:
                        nb = enc(ko.replace('·', '・'))
                        T = 0; k = e
                        while k < len(ob) and ob[k] == 0: T += 1; k += 1
                        region = (e - pos) + T
                        if len(nb) > region - 1:
                            nb = nb[:region-1]
                            while nb:
                                try: nb.decode('utf-8'); break
                                except UnicodeDecodeError: nb = nb[:-1]
                        body[pos:pos+len(nb)] = nb
                        body[pos+len(nb):pos+region] = b'\x00' * (region - len(nb))
                        ok += 1
                        if len(samples) < 8: samples.append(f"{fn}: {s[:30]}")
        pos = e + 1
    if not ok: continue
    stats['inj'] += ok
    loc = locate(ent["stored"], ent["flag"])
    rdbn, local, is10 = loc
    key = file_key(fn); f = DEP.f[rdbn]
    f.seek(local); hdr = bytearray(crypt_fast(f.read(32), key))
    if ent["flag"] == 0x20:
        comp = zlib.compress(bytes(body), 9)
        struct.pack_into("<I", hdr, 0x18, len(comp))
        nd = align_up(len(body), 4)
    else:
        comp = bytes(body)
        nd = align_up(32 + len(body), 4)
        struct.pack_into("<I", hdr, 0x18, nd)
    need = align_up(32 + len(comp), 4)
    if need <= gap_to_next(rdbn, local):
        struct.pack_into("<I", hdr, 0x1C, local // SECTOR)
        blob = bytearray(need); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(local); f.write(crypt_fast(bytes(blob), key))
        ns = ent["stored"]; stats['inplace'] += 1
    else:
        nl = cursor[rdbn]
        ns, sect = (nl // SECTOR + (0x1000000 if is10 else 0), nl // SECTOR)
        struct.pack_into("<I", hdr, 0x1C, sect)
        phys = align_up(max(nd, 32 + len(comp)), SECTOR)
        blob = bytearray(phys); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(nl); f.write(crypt_fast(bytes(blob), key))
        cursor[rdbn] = nl + phys; fsize[rdbn] = max(fsize[rdbn], cursor[rdbn])
        stats['reloc'] += 1
    struct.pack_into("<I", DEP.dec, ent["rec_off"], ns)
    struct.pack_into("<I", DEP.dec, ent["rec_off"]+4, nd)
    ent["stored"] = ns; ent["DEC_SIZE"] = nd
    stats['files'] += 1
    if nn % 200 == 0: print(f"  {nn}/{len(targets)} ({time.time()-t0:.0f}s)", flush=True)
enc_rdi = crypt_fast(bytes(DEP.dec), rdblib.RDI_KEY)
open(os.path.join('repack_out', 'RES00.RDI'), 'wb').write(enc_rdi)
DEP.close(); ORG.close()
print(f"완료 {time.time()-t0:.0f}s: {stats}")
print("표본:", *samples, sep='\n  ')
