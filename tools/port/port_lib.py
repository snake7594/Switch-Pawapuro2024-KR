# -*- coding: utf-8 -*-
"""1.8.0 → 1.15.0 이식 공용 라이브러리.

φ(문자열 오프셋 매핑) 구축 = 내용 기반. 오프셋은 버전마다 무효하므로
'같은 문자열의 몇 번째 출현인가'로 대응시키고, 개수가 다르면 이웃 앵커 창(window)으로 좁힌다.
"""
import os, sys, struct, pickle, time
import numpy as np

P18 = r"C:\Users\Jay\Desktop\z\파워풀2024-2025\추출원본-1.8.0\exefs\main"
P15 = r"C:\Users\Jay\Desktop\z\파워풀2024-2025\추출원본-1.15.0\exefs\main"
CACHE = r"C:\pawa_port\cache"


def load_nso(path):
    d = open(path, 'rb').read()
    u32 = lambda o: struct.unpack_from('<I', d, o)[0]
    h = dict(path=path, data=d, size=len(d),
             TEXT_FO=u32(0x10), TEXT_MO=u32(0x14), TEXT_SZ=u32(0x18),
             ROD_FO=u32(0x20), ROD_MO=u32(0x24), ROD_SZ=u32(0x28),
             DATA_FO=u32(0x30), DATA_MO=u32(0x34), DATA_SZ=u32(0x38),
             BSS_SZ=u32(0x3C))

    def va2fo(va):
        if h['TEXT_MO'] <= va < h['TEXT_MO'] + h['TEXT_SZ']: return va - h['TEXT_MO'] + h['TEXT_FO']
        if h['ROD_MO'] <= va < h['ROD_MO'] + h['ROD_SZ']:    return va - h['ROD_MO'] + h['ROD_FO']
        if h['DATA_MO'] <= va < h['DATA_MO'] + h['DATA_SZ']: return va - h['DATA_MO'] + h['DATA_FO']
        return None
    MOD0 = h['TEXT_FO'] + u32(h['TEXT_FO'] + 4)
    dfo = va2fo((MOD0 - h['TEXT_FO'] + h['TEXT_MO']) + struct.unpack_from('<i', d, MOD0 + 4)[0])
    DYN = {}
    o = dfo
    while True:
        t, v = struct.unpack_from('<QQ', d, o)
        if t == 0: break
        DYN.setdefault(t, v); o += 16
    h['DYN'] = DYN
    h['va2fo'] = va2fo
    h['MOD0_FO'] = MOD0
    h['RO_DELTA'] = h['ROD_MO'] - h['ROD_FO']
    h['RELA_FO'] = va2fo(DYN[7]); h['RELA_CNT'] = DYN[8] // 24
    h['RELA_END'] = h['RELA_FO'] + h['RELA_CNT'] * 24
    h['JMPREL_FO'] = va2fo(DYN[23]) if DYN.get(23) else None
    h['JMPREL_CNT'] = DYN.get(2, 0) // 24
    h['DYN_HI'] = va2fo(DYN[5]) + DYN[10] - 1          # STRTAB 끝 - 1
    h['STR_LO'] = h['DYN_HI'] + 1
    h['STR_END'] = h['ROD_FO'] + h['ROD_SZ']
    h['rela'] = np.frombuffer(d[h['RELA_FO']:h['RELA_END']], dtype='<u8').reshape(-1, 3)
    return h


def region_strings(h):
    """문자열영역의 NUL 구분 조각 (starts, ends) 절대 파일오프셋."""
    a = np.frombuffer(h['data'], dtype=np.uint8)[h['STR_LO']:h['STR_END']]
    nul = np.nonzero(a == 0)[0]
    starts = np.concatenate(([0], nul + 1)) + h['STR_LO']
    ends = np.concatenate((nul, [len(a)])) + h['STR_LO']
    return starts.astype(np.int64), ends.astype(np.int64)


def cstr(h, off):
    d = h['data']
    e = d.find(b'\x00', off)
    return d[off:e if e >= 0 else len(d)]


def occurrences(h, wantset, tag=''):
    """wantset(bytes) 각각의 등장 시작오프셋 목록."""
    t0 = time.time()
    starts, ends = region_strings(h)
    L = ends - starts
    want_lens = np.array(sorted({len(x) for x in wantset}), dtype=np.int64)
    m = np.isin(L, want_lens)
    idx = np.nonzero(m)[0]
    d = h['data']
    out = {}
    for i in idx.tolist():
        s = d[starts[i]:ends[i]]
        if s in wantset:
            out.setdefault(s, []).append(int(starts[i]))
    if tag:
        print(f"  [{tag}] 후보 {len(idx):,} → 매칭 고유 {len(out):,} ({time.time()-t0:.1f}s)", flush=True)
    return out


class PhiMap:
    """1.8.0 문자열 시작오프셋 → 1.15.0 문자열 시작오프셋."""

    def __init__(self, m, ambiguous, missing):
        self.m = m
        self.ambiguous = ambiguous
        self.missing = missing
        ks = np.array(sorted(m.keys()), dtype=np.int64)
        self.keys = ks
        self.vals = np.array([m[int(k)] for k in ks], dtype=np.int64)

    def __contains__(self, k): return k in self.m
    def get(self, k, default=None): return self.m.get(k, default)
    def __getitem__(self, k): return self.m[k]
    def __len__(self): return len(self.m)

    def window(self, off18):
        """off18 을 감싸는 앵커 구간의 1.15.0 창 (lo, hi)."""
        j = np.searchsorted(self.keys, off18)
        lo = int(self.vals[j - 1]) if j > 0 else -1
        hi = int(self.vals[j]) if j < len(self.vals) else 1 << 62
        return lo, hi

    def inversions(self):
        return int((np.diff(self.vals) <= 0).sum())


def build_phi(A, B, needed_offsets, tag='phi'):
    """needed_offsets(1.8.0 문자열 시작오프셋들) 에 대한 φ 구축."""
    needed = sorted(set(int(x) for x in needed_offsets))
    print(f"[{tag}] 대상 오프셋 {len(needed):,}", flush=True)
    sb = {}
    for o in needed:
        sb[o] = cstr(A, o)
    wantset = set(sb.values())
    print(f"[{tag}] 고유 문자열 {len(wantset):,}", flush=True)
    oa = occurrences(A, wantset, '1.8.0')
    ob = occurrences(B, wantset, '1.15.0')
    for v in oa.values(): v.sort()
    for v in ob.values(): v.sort()

    m, ambiguous, missing = {}, [], []
    for o in needed:
        s = sb[o]
        la, lb = oa.get(s), ob.get(s)
        if not lb:
            missing.append(o); continue
        if not la or o not in la:
            ambiguous.append(o); continue
        if len(la) == len(lb):
            m[o] = lb[la.index(o)]
        else:
            ambiguous.append(o)
    print(f"[{tag}] 1차: 확정 {len(m):,} · 모호 {len(ambiguous):,} · 소실 {len(missing):,}", flush=True)

    # 2차: 이웃 앵커 창으로 모호분 해소
    if m and ambiguous:
        phi0 = PhiMap(m, [], [])
        still = []
        for o in ambiguous:
            s = sb[o]
            lo, hi = phi0.window(o)
            cand = [x for x in ob[s] if lo < x < hi]
            if len(cand) == 1:
                m[o] = cand[0]
            else:
                still.append(o)
        ambiguous = still
        print(f"[{tag}] 2차(앵커창): 확정 {len(m):,} · 잔여 모호 {len(ambiguous):,}", flush=True)

    phi = PhiMap(m, ambiguous, missing)
    inv = phi.inversions()
    print(f"[{tag}] 단조성 위반 {inv:,} / 총 {len(phi):,}", flush=True)
    return phi


def cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, name)


def cached(name, fn):
    p = cache_path(name)
    if os.path.exists(p):
        with open(p, 'rb') as f: return pickle.load(f)
    v = fn()
    with open(p, 'wb') as f: pickle.dump(v, f, protocol=4)
    return v
