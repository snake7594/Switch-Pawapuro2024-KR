# -*- coding: utf-8 -*-
"""번역_마스터.json 을 1.15.0 좌표로 이식 → 번역_마스터_115.json"""
import sys, os, json, pickle, struct, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
from port_lib import load_nso, cache_path, P18, P15

WS = r"C:\pawa_ws_18"
OUT = r"C:\pawa_port"
os.makedirs(OUT, exist_ok=True)
t0 = time.time()
A = load_nso(P18); B = load_nso(P15)
o18, o15 = A['data'], B['data']
master = json.load(open(WS + r"\번역_마스터.json", encoding='utf-8'))
phi = pickle.load(open(cache_path('phi.pkl'), 'rb'))['m']
psi = pickle.load(open(cache_path('psi.pkl'), 'rb'))
print(f"φ {len(phi):,} · ψ {len(psi):,}")

# ---------- exe ----------
new_exe = []
st = dict(ok=0, nomap=0, mismatch=0, dyn=0)
lost_exe = []
for r in master['exe']:
    off = r['off']
    if off <= A['DYN_HI']: st['dyn'] += 1; continue
    n = phi.get(off)
    if n is None:
        st['nomap'] += 1; lost_exe.append(r); continue
    jpb = r['jp'].encode('utf-8')
    if o15[n:n+len(jpb)] != jpb or (n > 0 and o15[n-1] != 0):
        st['mismatch'] += 1; lost_exe.append(r); continue
    e = n + len(jpb); T = 0
    while e+T < len(o15) and o15[e+T] == 0: T += 1
    new_exe.append({'off': n, 'jp': r['jp'], 'ko': r['ko'], 'maxb': len(jpb) + T})
    st['ok'] += 1
print(f"exe: 이식 {st['ok']:,} / 원본 {len(master['exe']):,}  "
      f"(매핑없음 {st['nomap']:,} · 내용불일치 {st['mismatch']:,} · 동적영역 {st['dyn']:,})")

# maxb 변화 확인(정렬 패딩이 달라질 수 있음)
old = {r['off']: r['maxb'] for r in master['exe']}
grew = shrank = 0
tight = []
for r_new, r_old in zip(new_exe, [r for r in master['exe'] if phi.get(r['off']) is not None and r['off'] > A['DYN_HI']]):
    pass
mb_old = {}
for r in master['exe']:
    n = phi.get(r['off'])
    if n is not None: mb_old[n] = r['maxb']
for r in new_exe:
    a, b = mb_old.get(r['off']), r['maxb']
    if a is None: continue
    if b > a: grew += 1
    elif b < a: shrank += 1
print(f"     예산(maxb): 증가 {grew:,} · 감소 {shrank:,} · 동일 {len(new_exe)-grew-shrank:,}")

# ---------- exe_ext ----------
RFA, RFB = A['RELA_FO'], B['RELA_FO']
relaB = B['rela']
new_ext = []
se = dict(ok=0, nomap=0, noncontig=0, info=0, notarget=0)
lost_ext = []
for x in master['exe_ext']:
    idx = [(e - RFA)//24 for e in x['ents']]
    got = [psi.get(i) for i in idx]
    if any(g is None for g in got):
        se['nomap'] += 1; lost_ext.append(x); continue
    if any(int(relaB[g][1]) != 0x403 for g in got):
        se['info'] += 1; lost_ext.append(x); continue
    sj = sorted(got)
    if len(sj) >= 2 and any(sj[k+1]-sj[k] != 1 for k in range(len(sj)-1)):
        se['noncontig'] += 1; lost_ext.append(x); continue
    new_ext.append({'ko': x['ko'], 'ents': [RFB + g*24 for g in got]})
    se['ok'] += 1
print(f"exe_ext: 이식 {se['ok']:,} / 원본 {len(master['exe_ext']):,}  "
      f"(매핑없음 {se['nomap']:,} · 비연속 {se['noncontig']:,} · r_info {se['info']:,})")

# ents 중복 검사
seen = set(); dup = 0
for x in new_ext:
    for e in x['ents']:
        if e in seen: dup += 1
        seen.add(e)
print(f"     ents 중복 {dup:,}")

out = {'meta': dict(master.get('meta', {}), base='1.15.0',
                    ported_from='1.8.0', note='φ/ψ 좌표 이식'),
       'exe': new_exe, 'exe_ext': new_ext, 'rdb': master['rdb']}
json.dump(out, open(OUT + r"\번역_마스터_115.json", 'w', encoding='utf-8'), ensure_ascii=False)
json.dump({'exe': lost_exe, 'exe_ext': [{'ko': x['ko']} for x in lost_ext]},
          open(OUT + r"\_port_lost.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"→ {OUT}\\번역_마스터_115.json  ({time.time()-t0:.1f}s)")
print("소실 exe 원문 샘플:", [r['jp'][:30] for r in lost_exe[:10]])
