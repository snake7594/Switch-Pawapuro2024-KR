# -*- coding: utf-8 -*-
"""원본 RDB → 한국어 RDB 재빌드.

  원본 CHK 본문  ─(1)─▶ 번역_마스터.json 텍스트 제자리 주입
                 ─(2)─▶ 잔차 팩 적용(폰트 글리프·번역 이미지·마스터 미포함 차이)
                 ─────▶ repack_out/RES00.RDB · RES00.RDI · RES10.RDB

사용:
    set PAWA_ROOT=<작업공간>
    python tools/BUILD_RDB_FROM_MASTER.py [--fresh] [--no-residual]

입력(작업공간): RES00.RDB, RES00.RDI, RES10.RDB(원본), 번역_마스터.json,
                !exefs-작업/hangul_to_hanja.tsv, rdb_residual.pack
출력: repack_out/  (약 7.3GB, 수 분~십수 분 소요)

주의: 잔차 팩은 '원본+마스터텍스트' 로 설명되지 않는 부분을 그대로 재현하기 위한 것입니다.
      잔차가 걸린 파일(FONT/이미지 등 소수)의 텍스트를 마스터에서 수정하면 잔차가 덮어쓸 수
      있습니다. 그 경우 --no-residual 로 확인해 보세요(폰트·이미지 번역은 빠집니다).
"""
import sys, os, json, zlib, struct, time, bisect, shutil
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rdblib
from rdblib import align_up, file_key, crypt_fast, SECTOR, locate

FRESH = '--fresh' in sys.argv
USE_RES = '--no-residual' not in sys.argv
SRC = ('RES00.RDB', 'RES00.RDI', 'RES10.RDB')

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')
def fit(nb, region):
    if len(nb) > region - 1:
        nb = nb[:region-1]
        while nb:
            try: nb.decode('utf-8'); break
            except UnicodeDecodeError: nb = nb[:-1]
    return nb

# ---------- 잔차 팩 로드 ----------
RES = {}
if USE_RES:
    cand = [p for p in ('rdb_residual.pack',
                        os.path.join(os.path.dirname(os.path.dirname(
                            os.path.abspath(__file__))), 'data', 'rdb_residual.pack'))
            if os.path.exists(p)]
    if not cand:
        print("⚠ rdb_residual.pack 없음 → 폰트·이미지 번역이 빠집니다(--no-residual 과 동일)")
        USE_RES = False
    else:
        raw = zlib.decompress(open(cand[0], 'rb').read())
        assert raw[:6] == b'PWRES2', "잔차 팩 형식 오류"
        o = 6; (cnt,) = struct.unpack_from('<I', raw, o); o += 4
        for _ in range(cnt):
            (nl,) = struct.unpack_from('<H', raw, o); o += 2
            nm = raw[o:o+nl].decode('utf-8'); o += nl
            mode, flen = struct.unpack_from('<BI', raw, o); o += 5
            if mode == 1:
                (bl,) = struct.unpack_from('<I', raw, o); o += 4
                RES[nm] = ('full', flen, raw[o:o+bl]); o += bl
            else:
                (rn,) = struct.unpack_from('<I', raw, o); o += 4
                runs = []
                for _ in range(rn):
                    off, ln = struct.unpack_from('<II', raw, o); o += 8
                    runs.append((off, raw[o:o+ln])); o += ln
                RES[nm] = ('runs', flen, runs)
        print(f"잔차 팩: {len(RES):,}개 파일 ({cand[0]})")

# ---------- 원본 → repack_out ----------
os.makedirs('repack_out', exist_ok=True)
for fn in SRC:
    dst = os.path.join('repack_out', fn)
    if FRESH or not os.path.exists(dst):
        if not os.path.exists(fn):
            sys.exit(f"원본 {fn} 이 작업공간에 없습니다. tools/SETUP_WORKSPACE.py 를 먼저 실행하세요.")
        print(f"복사 {fn} ({os.path.getsize(fn)/1073741824:.2f}GB) …", flush=True)
        shutil.copy2(fn, dst)

master = json.load(open('번역_마스터.json', encoding='utf-8'))
byfile = {}
for r in master['rdb']: byfile.setdefault(r['file'], []).append(r)
targets = set(byfile) | set(RES)
print(f"대상: 텍스트 {len(master['rdb']):,}건 / 파일 {len(targets):,}개")

# ---------- 주입 ----------
DEP = rdblib.RDB('repack_out', writable=True)
laid = {"RES00.RDB": [], "RES10.RDB": []}
for t in DEP.table:
    loc = locate(t["stored"], t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
fsize = {n: os.path.getsize(os.path.join('repack_out', n)) for n in DEP.f}
# ⚠제자리 쓰기의 상한은 '원본 끝'으로 고정한다. 재배치로 파일이 커진다고 해서 마지막 파일의
#   여유가 늘어나는 것이 아니다(그 뒤는 재배치 영역). 고정하지 않으면 재배치본을 덮어써
#   해당 CHK 가 깨진다(zlib 해제 실패).
base_end = dict(fsize)
def gap(rdb, local):
    arr = laid[rdb]; j = bisect.bisect_right(arr, local)
    return (arr[j] if j < len(arr) else base_end[rdb]) - local
cursor = {n: align_up(fsize[n], SECTOR) for n in DEP.f}

st = dict(files=0, text=0, res=0, inplace=0, reloc=0, skip=0)
t0 = time.time()
for fn in sorted(targets):
    ent = DEP.idx.get(fn)
    if not ent or ent['flag'] not in (0, 0x20): st['skip'] += 1; continue
    try: body = bytearray(DEP.read_body(fn))
    except Exception: st['skip'] += 1; continue
    before = bytes(body)

    for r in byfile.get(fn, []):                     # (1) 텍스트 제자리 주입
        off = r['off']; oe = body.find(b'\x00', off)
        if oe < 0: continue
        T = 0; k = oe
        while k < len(body) and body[k] == 0: T += 1; k += 1
        region = (oe - off) + T
        nb = fit(enc(r['ko']), region)
        body[off:off+region] = bytes(nb) + b'\x00' * (region - len(nb))
        st['text'] += 1
    if fn in RES:                                    # (2) 잔차 적용
        mode, flen, payload = RES[fn]
        if mode == 'full': body = bytearray(payload)
        else:
            for off, blob in payload: body[off:off+len(blob)] = blob
        st['res'] += 1
    if bytes(body) == before: continue

    loc = locate(ent["stored"], ent["flag"]); rdbn, local, is10 = loc
    key = file_key(fn); f = DEP.f[rdbn]
    f.seek(local); hdr = bytearray(crypt_fast(f.read(32), key))
    if ent["flag"] == 0x20:
        comp = zlib.compress(bytes(body), 9)
        struct.pack_into("<I", hdr, 0x18, len(comp)); nd = align_up(len(body), 4)
    else:
        comp = bytes(body); nd = align_up(32+len(body), 4)
        struct.pack_into("<I", hdr, 0x18, nd)
    need = align_up(32+len(comp), 4)
    if need <= gap(rdbn, local):                     # 제자리
        struct.pack_into("<I", hdr, 0x1C, local // SECTOR)
        blob = bytearray(need); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(local); f.write(crypt_fast(bytes(blob), key)); ns = ent["stored"]; st['inplace'] += 1
    else:                                            # 뒤 빈 섹터로 재배치
        nl = cursor[rdbn]; ns, sect = (nl//SECTOR + (0x1000000 if is10 else 0), nl//SECTOR)
        struct.pack_into("<I", hdr, 0x1C, sect)
        phys = align_up(max(nd, 32+len(comp)), SECTOR)
        blob = bytearray(phys); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(nl); f.write(crypt_fast(bytes(blob), key))
        cursor[rdbn] = nl + phys; fsize[rdbn] = max(fsize[rdbn], cursor[rdbn]); st['reloc'] += 1
    struct.pack_into("<I", DEP.dec, ent["rec_off"], ns)
    struct.pack_into("<I", DEP.dec, ent["rec_off"]+4, nd)
    ent["stored"] = ns; ent["DEC_SIZE"] = nd; st['files'] += 1
    if st['files'] % 200 == 0: print(f"  …{st['files']}파일 ({time.time()-t0:.0f}s)", flush=True)

open(os.path.join('repack_out', 'RES00.RDI'), 'wb').write(crypt_fast(bytes(DEP.dec), rdblib.RDI_KEY))
DEP.close()
print(f"완료 {st} ({time.time()-t0:.0f}s)")
print("→ repack_out/RES00.RDB, RES00.RDI, RES10.RDB")
print("   검증: tools/VERIFY_BUILD.py 로 MD5를 확인하세요.")
