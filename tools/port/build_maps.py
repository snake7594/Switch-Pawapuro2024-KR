# -*- coding: utf-8 -*-
"""φ(master 문자열 오프셋) + ψ(RELA 인덱스) 매핑 구축.

φ : master['exe'] 의 off 만 대상. 같은 문자열의 '몇 번째 출현'인가로 대응(출현수 일치 시 확정).
ψ : RELA 테이블 두 개를 시퀀스로 보고 patience diff.
     토큰 = addend 가 가리키는 '문자열 내용'(버전 무관) → 앵커 → LIS → 구간별 SequenceMatcher.
"""
import sys, os, json, pickle, time
from collections import Counter, defaultdict
from bisect import bisect_left
import difflib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
from port_lib import load_nso, build_phi, cache_path, P18, P15

WS = r"C:\pawa_ws_18"
t0 = time.time()
A = load_nso(P18); B = load_nso(P15)
master = json.load(open(WS + r"\번역_마스터.json", encoding='utf-8'))
print(f"로드 {time.time()-t0:.1f}s", flush=True)

# ================= φ =================
need = set(r['off'] for r in master['exe'] if r['off'] > A['DYN_HI'])
phi = build_phi(A, B, need, 'φ')
with open(cache_path('phi.pkl'), 'wb') as f:
    pickle.dump({'m': phi.m, 'ambiguous': phi.ambiguous, 'missing': phi.missing}, f, protocol=4)
print(f"φ 저장 완료 ({time.time()-t0:.1f}s)\n", flush=True)

# ================= ψ =================
def tokens(h, sid):
    ad = h['rela'][:, 2].astype(np.int64)
    ri = h['rela'][:, 1].astype(np.int64)
    fo = ad - h['RO_DELTA']
    inreg = (fo > h['DYN_HI']) & (fo < h['STR_END'])
    d = h['data']
    cache = {}
    out = np.empty(len(ad), dtype=np.int64)
    for k in range(len(ad)):
        if not inreg[k]:
            out[k] = -1 - (int(ri[k]) & 0xffff)
            continue
        f = int(fo[k])
        t = cache.get(f)
        if t is None:
            e = d.find(b'\x00', f)
            s = d[f:e if e >= 0 else f]
            t = sid.get(s)
            if t is None:
                t = len(sid); sid[s] = t
            cache[f] = t
        out[k] = t
    return out.tolist()

sid = {}
t1 = time.time()
ta = tokens(A, sid); print(f"토큰 A {len(ta):,} (고유문자열 {len(sid):,}) {time.time()-t1:.1f}s", flush=True)
t1 = time.time()
tb = tokens(B, sid); print(f"토큰 B {len(tb):,} (고유문자열 {len(sid):,}) {time.time()-t1:.1f}s", flush=True)

def lis_pairs(pairs):
    """pairs: i 오름차순. j 에 대한 최장증가부분수열 선택."""
    tails, tails_idx, prev = [], [], [-1]*len(pairs)
    for k, (i, j) in enumerate(pairs):
        p = bisect_left(tails, j)
        if p == len(tails):
            tails.append(j); tails_idx.append(k)
        else:
            tails[p] = j; tails_idx[p] = k
        prev[k] = tails_idx[p-1] if p > 0 else -1
    out = []
    k = tails_idx[-1] if tails_idx else -1
    while k >= 0:
        out.append(pairs[k]); k = prev[k]
    out.reverse()
    return out

ca, cb = Counter(ta), Counter(tb)
posb = {t: j for j, t in enumerate(tb) if cb[t] == 1}
anchors = [(i, posb[t]) for i, t in enumerate(ta) if ca[t] == 1 and t in posb]
print(f"유일토큰 앵커 후보 {len(anchors):,}", flush=True)
anchors = lis_pairs(anchors)
print(f"LIS 단조 앵커 {len(anchors):,} ({time.time()-t0:.1f}s)", flush=True)

psi = {i: j for i, j in anchors}
gaps = 0; filled = 0
bounds = [(-1, -1)] + anchors + [(len(ta), len(tb))]
for (i0, j0), (i1, j1) in zip(bounds, bounds[1:]):
    la, lb = ta[i0+1:i1], tb[j0+1:j1]
    if not la or not lb: continue
    gaps += 1
    if len(la) * len(lb) > 4_000_000:      # 과대 구간은 앞뒤 동일 접두/접미만
        n = 0
        while n < min(len(la), len(lb)) and la[n] == lb[n]:
            psi[i0+1+n] = j0+1+n; n += 1; filled += 1
        m = 0
        while m < min(len(la), len(lb)) - n and la[-1-m] == lb[-1-m]:
            psi[i1-1-m] = j1-1-m; m += 1; filled += 1
        continue
    sm = difflib.SequenceMatcher(None, la, lb, autojunk=False)
    for bi, bj, sz in sm.get_matching_blocks():
        for k in range(sz):
            psi[i0+1+bi+k] = j0+1+bj+k; filled += 1
print(f"구간 {gaps:,} 채움 {filled:,} → ψ {len(psi):,} / {len(ta):,} ({time.time()-t0:.1f}s)", flush=True)

ks = np.array(sorted(psi.keys())); vs = np.array([psi[int(k)] for k in ks])
print(f"ψ 단조성 위반 {int((np.diff(vs) <= 0).sum()):,}")
ri_a = A['rela'][:, 1]; ri_b = B['rela'][:, 1]
print(f"ψ r_info 불일치 {int((ri_a[ks] != ri_b[vs]).sum()):,}")
with open(cache_path('psi.pkl'), 'wb') as f:
    pickle.dump(psi, f, protocol=4)

# --- 검증: exe_ext ents ---
RELA_FO_A = A['RELA_FO']
tot = ok = sent_ok = 0
for x in master['exe_ext']:
    ents = [(e - RELA_FO_A)//24 for e in x['ents']]
    tot += len(ents)
    got = [psi.get(i) for i in ents]
    ok += sum(1 for g in got if g is not None)
    if all(g is not None for g in got):
        sj = sorted(got)
        if all(sj[k+1]-sj[k] == 1 for k in range(len(sj)-1)): sent_ok += 1
print(f"\nexe_ext: ents {tot:,} 중 매핑 {ok:,} ({ok/tot*100:.2f}%) · "
      f"문장 {len(master['exe_ext']):,} 중 완전이식 {sent_ok:,} ({sent_ok/len(master['exe_ext'])*100:.2f}%)")
print(f"총 {time.time()-t0:.1f}s")
