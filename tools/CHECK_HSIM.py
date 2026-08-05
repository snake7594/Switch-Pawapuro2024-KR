# -*- coding: utf-8 -*-
"""고교(栄冠ナイン) 모드 로드 CHK 무결성 검사: repack_out vs 원본 root RDB.
검사: 복호·zlib해제 성공 / body 크기 / STRING 청크(포인터테이블 경계·N·종료자) / 구조바이트."""
import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib

ORG = rdblib.RDB('.')
DEP = rdblib.RDB('repack_out')

def check_string_chunk(body):
    """STRING 청크 구조 검증. 반환: (ok, msg)."""
    si = body.find(b'STRING')
    if si < 0: return True, 'STRING없음(비대상)'
    base = si + 0x10
    if base + 4 > len(body): return False, 'base 초과'
    p0 = struct.unpack_from('<I', body, base)[0]
    if p0 < 4 or p0 % 4: return False, f'p0불량 {p0}'
    N = p0 // 4
    if base + 4*N > len(body): return False, f'포인터테이블 초과 N={N}'
    size1 = struct.unpack_from('<I', body, si+8)[0]
    # 각 문자열: 오프셋 경계 + 종료자 존재
    for k in range(N):
        off = struct.unpack_from('<I', body, base+4*k)[0]
        s = base + off
        if s >= len(body): return False, f'문자열[{k}] 오프셋 초과 {off}'
        e = body.find(b'\x00', s)
        if e < 0: return False, f'문자열[{k}] 종료자 없음(런어웨이 위험)'
        # UTF-8 유효성
        try: body[s:e].decode('utf-8')
        except UnicodeDecodeError: return False, f'문자열[{k}] UTF-8 깨짐 @0x{s:x}'
    # STRING 청크 경계(size1) 안에 body가 있나
    if si + size1 > len(body) + 16: return False, f'size1 과대 {size1} vs body {len(body)}'
    return True, f'OK (N={N})'

names = [n for n in DEP.idx if n.startswith(('HSIM', 'HATK', 'D2D_HATK', 'G2D_HATK')) or n in
         ('TEXT_HSIMSCH.CHK', 'CHALLENGE.CHK', 'TEXT_CHAL_STR.CHK', 'LIVE_STG.CHK')]
print(f"검사 대상 {len(names)}개")
bad = []
for name in sorted(names):
    try:
        db = DEP.read_body(name)
    except Exception as e:
        bad.append((name, f'복호/해제 실패: {e}')); continue
    if db is None:
        continue
    try:
        ob = ORG.read_body(name)
    except Exception:
        ob = None
    ok, msg = check_string_chunk(db)
    sz = f' body {len(db)}' + (f'/orig {len(ob)}' if ob else '')
    if not ok:
        bad.append((name, msg + sz))
        print(f'  ★ {name}: {msg}{sz}')
    # 크기 급변(반토막/폭증) 경고
    if ob and len(db) != len(ob):
        d = len(db) - len(ob)
        if abs(d) > len(ob) * 0.3:
            print(f'  ⚠ {name}: 크기 {len(ob)}→{len(db)} ({d:+})')
print('=' * 50)
print(f"구조손상 {len(bad)}개")
for n, m in bad: print(f'  {n}: {m}')
ORG.close(); DEP.close()
