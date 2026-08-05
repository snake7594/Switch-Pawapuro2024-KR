# -*- coding: utf-8 -*-
"""잔여 미번역 주입: _untr_rdb.json(occurrence) × [사전 + _untr_tr.json(워크플로 번역)] → repack_out.
파일별로 모아 제자리 슬랙 주입(클린 절단) → 재압축 → gap 제자리/끝 재배치 → RDI 갱신 → 재독 검증."""
import sys, os, json, zlib, struct, time
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
def charfix(s): return s.replace('·', '・').replace('—', 'ー')

u = json.load(open('_untr_rdb.json', encoding='utf-8'))
d = json.load(open('_dict_jpko.json', encoding='utf-8'))
tr = {}
if os.path.isfile('_untr_tr.json'):
    full = json.load(open('_untr_full.json', encoding='utf-8'))
    trmap = {r['i']: (r.get('ko') or '').strip() for r in json.load(open('_untr_tr.json', encoding='utf-8'))}
    for item in full:
        ko = trmap.get(item['i'])
        if ko: tr[item['jp']] = ko

# 파일별 패치 목록
byfile = {}
n_dict = n_tr = n_none = 0
for jp, v in u.items():
    ko = d.get(jp) or tr.get(jp)
    if not ko:
        n_none += 1; continue
    if jp in d: n_dict += 1
    else: n_tr += 1
    kob = enc(charfix(ko))
    for (fn, off, budget) in v['occ']:
        byfile.setdefault(fn, []).append((off, budget, kob, jp))
print(f"사전 {n_dict} + 신규번역 {n_tr} 고유, 미해결 {n_none}; 대상 파일 {len(byfile)}")

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
stats = dict(files=0, patched=0, trunc=0, inplace=0, reloc=0)
t0 = time.time()
for fn, patches in sorted(byfile.items()):
    ent = DEP.idx.get(fn)
    if not ent or ent['flag'] not in (0, 0x20): continue
    try: body = bytearray(DEP.read_body(fn))
    except Exception as e:
        print(f'  [스킵] {fn}: {e}'); continue
    ok = 0
    for (off, budget, kob, jp) in patches:
        # 현재 그 위치가 여전히 원본 jp인지 확인(안전)
        e = body.find(b'\x00', off)
        if e <= off: continue
        try: cur = bytes(body[off:e]).decode('utf-8')
        except UnicodeDecodeError: continue
        if cur != jp: continue
        nb = kob
        region = budget + 1
        if len(nb) > region - 1:
            nb = nb[:region-1]
            while nb:
                try: nb.decode('utf-8'); break
                except UnicodeDecodeError: nb = nb[:-1]
            stats['trunc'] += 1
        # region 재계산(실제 슬랙)
        T = 0; k = e
        while k < len(body) and body[k] == 0: T += 1; k += 1
        region = (e - off) + T
        if len(nb) > region - 1:
            nb = nb[:region-1]
            while nb:
                try: nb.decode('utf-8'); break
                except UnicodeDecodeError: nb = nb[:-1]
        body[off:off+len(nb)] = nb
        body[off+len(nb):off+region] = b'\x00' * (region - len(nb))
        ok += 1
    if not ok: continue
    stats['patched'] += ok
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
print(f"완료 {time.time()-t0:.0f}s: {stats}")

# 검증: SEN_TEXT_2ND 재독 + 표본
V = rdblib.RDB('repack_out')
nb = V.read_body('SEN_TEXT_2ND.CHK'); V.close()
tsv_r = {v: k for k, v in TSV.items()}
smp = []
pos = 0
while pos < len(nb) and len(smp) < 4:
    e = nb.find(b'\x00', pos)
    if e < 0: break
    if 30 <= e - pos <= 200:
        try:
            s = ''.join(tsv_r.get(c, c) for c in nb[pos:e].decode('utf-8'))
            if sum(1 for c in s if '가' <= c <= '힣') > 10: smp.append(s[:46])
        except UnicodeDecodeError: pass
    pos = e + 1
print("SEN_TEXT_2ND 표본:")
for s in smp: print("  ", s)
