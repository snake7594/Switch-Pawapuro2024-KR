# -*- coding: utf-8 -*-
"""1.15.0 용 잔차 팩 생성.

  기존 팩  - COMMON_2D_ADD.CHK (1.15.0 에서 삭제된 파일)
           + COMMON_2D_2ND.CHK (1.15.0 신규 폰트, 한글 글리프 주입분을 runs 로)
사용: python BUILD_RESIDUAL_115.py <기존팩> <원본RDB폴더> <한글2ND본문> <출력팩>
"""
import sys, os, zlib, struct, hashlib
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"C:\Users\Jay\Desktop\z\파워풀2024-2025\Switch-Pawapuro2024-KR\tools")
from rdblib import RDB

DROP = {'COMMON_2D_ADD.CHK'}

def read_pack(p):
    raw = zlib.decompress(open(p, 'rb').read())
    assert raw[:6] == b'PWRES2'
    o = 6; (cnt,) = struct.unpack_from('<I', raw, o); o += 4
    out = []
    for _ in range(cnt):
        (nl,) = struct.unpack_from('<H', raw, o); o += 2
        nm = raw[o:o+nl].decode('utf-8'); o += nl
        mode, flen = struct.unpack_from('<BI', raw, o); o += 5
        if mode == 1:
            (bl,) = struct.unpack_from('<I', raw, o); o += 4
            out.append((nm, 1, flen, raw[o:o+bl])); o += bl
        else:
            (rn,) = struct.unpack_from('<I', raw, o); o += 4
            runs = []
            for _ in range(rn):
                off, ln = struct.unpack_from('<II', raw, o); o += 8
                runs.append((off, raw[o:o+ln])); o += ln
            out.append((nm, mode, flen, runs))
    return out

def write_pack(entries, p):
    buf = bytearray(b'PWRES2')
    buf += struct.pack('<I', len(entries))
    for nm, mode, flen, payload in entries:
        nb = nm.encode('utf-8')
        buf += struct.pack('<H', len(nb)) + nb + struct.pack('<BI', mode, flen)
        if mode == 1:
            buf += struct.pack('<I', len(payload)) + payload
        else:
            buf += struct.pack('<I', len(payload))
            for off, blob in payload:
                buf += struct.pack('<II', off, len(blob)) + blob
    open(p, 'wb').write(zlib.compress(bytes(buf), 9))

def make_runs(a, b, gap=16):
    """a→b 차이를 (off, bytes) 런 목록으로. gap 이하 간격은 병합."""
    assert len(a) == len(b)
    runs = []
    i = 0; n = len(a)
    while i < n:
        if a[i] == b[i]: i += 1; continue
        s = i; last = i
        while i < n:
            if a[i] != b[i]: last = i
            elif i - last > gap: break
            i += 1
        runs.append((s, bytes(b[s:last+1])))
        i = last + 1
    return runs

def main(old_pack, rdbdir, kor2nd, out_pack):
    allents = read_pack(old_pack)
    ents = [e for e in allents if e[0] not in DROP]
    print(f"기존 {len(allents)} → 삭제 후 {len(ents)}")
    R = RDB(rdbdir)
    o2n = R.read_body('COMMON_2D_2ND.CHK')
    R.close()
    kor = open(kor2nd, 'rb').read()
    assert len(kor) == len(o2n), f"길이 불일치 {len(kor)} vs {len(o2n)}"
    runs = make_runs(o2n, kor)
    print(f"COMMON_2D_2ND runs {len(runs):,}  페이로드 {sum(len(b) for _, b in runs):,}B")
    chk = bytearray(o2n)
    for off, blob in runs: chk[off:off+len(blob)] = blob
    assert bytes(chk) == kor, "runs 재구성 불일치"
    ents.append(('COMMON_2D_2ND.CHK', 2, len(o2n), runs))
    ents.sort(key=lambda e: e[0])
    write_pack(ents, out_pack)
    print(f"→ {out_pack} {os.path.getsize(out_pack):,}B  파일 {len(ents)}개")
    back = {e[0]: e for e in read_pack(out_pack)}
    chk2 = bytearray(o2n)
    for off, blob in back['COMMON_2D_2ND.CHK'][3]: chk2[off:off+len(blob)] = blob
    assert bytes(chk2) == kor and back['COMMON_2D_2ND.CHK'][2] == len(o2n)
    print("   재읽기 검증 OK")

if __name__ == '__main__':
    main(*sys.argv[1:5])
