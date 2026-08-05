# -*- coding: utf-8 -*-
"""과복원된 실텍스트 파일 사전 재주입(NAME_DIC/SEN_*/PEN_* 등; 栄冠 HSIM/HATK 제외=안전우선).
방법: 파일 내 NUL경계 원문(jp) 정확일치 → dict ko → tsv 주입(슬랙, 클린절단)."""
import sys, os, json, zlib, struct, time, re
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib
from rdblib import align_up, file_key, crypt_fast, SECTOR, locate

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
targets = [f for f in rep if textpat.match(f)]
print(f"재주입 대상 파일 {len(targets)}")

DEP = rdblib.RDB('repack_out', writable=True)
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
for fn in targets:
    ent = DEP.idx.get(fn)
    if not ent or ent['flag'] not in (0, 0x20): continue
    try: body = bytearray(DEP.read_body(fn))
    except Exception: continue
    ok = 0
    pos = 0
    while pos < len(body):
        e = body.find(b'\x00', pos)
        if e < 0: break
        if 4 <= e - pos <= 300:
            seg = bytes(body[pos:e])
            try: s = seg.decode('utf-8')
            except UnicodeDecodeError: s = None
            if s:
                ko = DICT.get(s)
                if ko:
                    nb = enc(ko.replace('·', '・'))
                    T = 0; k = e
                    while k < len(body) and body[k] == 0: T += 1; k += 1
                    region = (e - pos) + T
                    if len(nb) > region - 1:
                        nb = nb[:region-1]
                        while nb:
                            try: nb.decode('utf-8'); break
                            except UnicodeDecodeError: nb = nb[:-1]
                    body[pos:pos+len(nb)] = nb
                    body[pos+len(nb):pos+region] = b'\x00' * (region - len(nb))
                    ok += 1
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
enc_rdi = crypt_fast(bytes(DEP.dec), rdblib.RDI_KEY)
open(os.path.join('repack_out', 'RES00.RDI'), 'wb').write(enc_rdi)
DEP.close()
print(f"완료: {stats}")
