# -*- coding: utf-8 -*-
"""작업공간(workspace) 구성 — 저장소 데이터 + 사용자 원본 게임파일 → 빌드 가능한 상태로.

사용법:
    python tools/SETUP_WORKSPACE.py <작업공간경로> [--orig <원본4파일이_있는_폴더>] [--link]

하는 일:
 1) 원본 4파일(main, RES00.RDB, RES00.RDI, RES10.RDB) 존재·MD5 확인 (게임 업데이트 v1.15.0 기준)
 2) 저장소 data/ 를 작업공간에 배치(도구들이 기대하는 이름·위치로)
 3) BUILD_BASE.py 로 베이스 실행파일 생성 → inject_out/main-base
    (v1.4 까지 쓰던 bootstrap xdelta 는 더 이상 필요 없다 — 베이스가 마스터에서 결정적으로 재생성된다)
 4) inject_out/ repack_out/ 생성
이후:  set PAWA_ROOT=<작업공간>  →  python tools/BUILD_EXE.py
"""
import sys, os, shutil, hashlib, subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG_MD5 = {'main':      '9164c7dc613bc2a447582ccee64c2256',
            'RES00.RDB': '46ccf287fd62e9e2d51b193e788555a0',
            'RES00.RDI': '3642336a108111be55a6851d3f2328db',
            'RES10.RDB': 'f31f0418f0d6096d848fde10511c0878'}
LAYOUT = [('data/번역_마스터.json', '번역_마스터.json'),
          ('data/hangul_to_hanja.tsv', '!exefs-작업/hangul_to_hanja.tsv'),
          ('data/rdb_residual.pack', 'rdb_residual.pack'),
          ('data/마이라이프_대사.json', '마이라이프_대사.json'),
          ('data/전체대사_재구성.json', '전체대사_재구성.json')]

def md5(p, chunk=1 << 24):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()

def place(src, dst, link):
    if os.path.exists(dst): os.remove(dst)
    if link:
        try:
            os.link(src, dst); return 'hardlink'
        except OSError:
            pass
    shutil.copy2(src, dst); return 'copy'

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    sys.stdout.reconfigure(encoding='utf-8')
    ws = os.path.abspath(sys.argv[1])
    orig = os.path.abspath(sys.argv[sys.argv.index('--orig')+1]) if '--orig' in sys.argv else ws
    link = '--link' in sys.argv
    os.makedirs(ws, exist_ok=True)
    print(f"작업공간 : {ws}\n원본폴더 : {orig}\n저장소   : {REPO}\n")

    print("[1/4] 원본 게임파일 확인 (게임 업데이트 v1.15.0)")
    for fn, want in ORIG_MD5.items():
        src = os.path.join(orig, fn); dst = os.path.join(ws, fn)
        if not os.path.exists(src) and os.path.exists(dst): src = dst
        if not os.path.exists(src):
            print(f"  ✗ {fn} 없음 — 본인 게임 덤프에서 준비하세요"
                  f"\n     main=ExeFS,  RES00.RDB/RES00.RDI/RES10.RDB=RomFS의 cdvdroot/")
            sys.exit(1)
        got = md5(src)
        ok = (got == want)
        print(f"  {'✓' if ok else '✗'} {fn:12s} {got}{'' if ok else '  ← 기대 '+want}")
        if not ok:
            print("     MD5 불일치: 2024-2025 최신 업데이트(v1.15.0) 적용 상태로 덤프했는지 확인하세요.")
            print("     (구 v1.8.0 덤프는 더 이상 지원하지 않습니다 — 게임을 업데이트하세요.)")
            sys.exit(1)
        if os.path.abspath(src) != os.path.abspath(dst):
            how = place(src, dst, link)
            print(f"     {how} 완료 ({os.path.getsize(dst)/1048576:.0f}MB)")

    print("\n[2/4] 번역 데이터 배치")
    for s, d in LAYOUT:
        sp = os.path.join(REPO, s.replace('/', os.sep))
        dp = os.path.join(ws, d.replace('/', os.sep))
        if not os.path.exists(sp): print(f"  ⚠ 저장소에 없음: {s}"); continue
        os.makedirs(os.path.dirname(dp) or '.', exist_ok=True)
        shutil.copy2(sp, dp)
        print(f"  ✓ {d}  ({os.path.getsize(dp)/1048576:.1f}MB)")

    print("\n[3/4] 베이스 실행파일 생성 (풀 리다이렉트 계층)")
    io = os.path.join(ws, 'inject_out'); os.makedirs(io, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(REPO, 'tools', 'BUILD_BASE.py'),
                        os.path.join(ws, 'main'), os.path.join(ws, '번역_마스터.json'),
                        os.path.join(ws, '!exefs-작업', 'hangul_to_hanja.tsv'),
                        os.path.join(io, 'main-base')])
    if r.returncode != 0: print("  ✗ BUILD_BASE 실패"); sys.exit(1)

    print("\n[4/4] 출력 폴더")
    for d in ('inject_out', 'repack_out'):
        os.makedirs(os.path.join(ws, d), exist_ok=True); print(f"  ✓ {d}/")

    print(f"""
완료. 다음 단계:

  Windows(cmd) :  set PAWA_ROOT={ws}
  PowerShell   :  $env:PAWA_ROOT="{ws}"
  Linux/macOS  :  export PAWA_ROOT={ws}

  실행파일 빌드 :  python tools/BUILD_EXE.py              → inject_out/main-built
  RDB 빌드      :  python tools/BUILD_RDB_FROM_MASTER.py  → repack_out/RES00.RDB 등
""")

if __name__ == '__main__':
    main()
