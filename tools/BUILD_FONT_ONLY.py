# -*- coding: utf-8 -*-
"""
폰트 전용 빠른 빌드 (원인 격리용)
=================================
한글 폰트 2개만 원본에 주입해서 빌드한다. 텍스트/실행파일 주입은 하지 않는다.
 - COMMON_2D.CHK      → RES00.RDB (제자리 패치 가능 확인됨)
 - COMMON_2D_ADD.CHK  → RES10.RDB (제자리 패치 가능 확인됨)

[속도] 6.6GB 통째 재압축/재기록 없이:
 1) 원본 RES00.RDB / RES10.RDB 를 robocopy /J(무버퍼 고속복사)로 출력폴더에 복사(1회)
 2) 폰트 슬롯만 제자리(seek+write) 패치 (~수 MB, 수 초)
 3) RDI 2개 항목만 갱신
[--reuse] 이미 build_fontonly/ 에 복사본이 있으면 재복사 생략하고 폰트만 다시 제자리패치
          (폰트를 새 버전으로 바꿔 반복 테스트할 때 매우 빠름)

출력: build_fontonly/RES00.RDB · RES10.RDB · RES00.RDI
배포: romfs-.../cdvdroot/ 에 이 3개 복사(덮어쓰기). exe(main)는 원본 그대로 사용.
"""
import os, sys, zlib, struct, subprocess, time, shutil
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__)); os.chdir(ROOT)
sys.path.insert(0, ROOT)
import REPACK_AUTO as R

OUT_DIR = "build_fontonly"
REUSE = "--reuse" in sys.argv
NO_VERIFY = "--no-verify" in sys.argv

# 주입할 폰트: 아카이브명 -> 편집파일
FONTS = {
    "COMMON_2D.CHK":     "COMMON_2D-한글폰트삽입.CHK",
    "COMMON_2D_ADD.CHK": "COMMON_2D_ADD-한글폰트삽입.CHK",
}

def robocopy(src_name, dst_dir):
    """robocopy /J 로 단일 파일 고속 복사. 성공 시 True."""
    t0 = time.time()
    p = subprocess.run(
        ["robocopy", ".", dst_dir, src_name, "/J", "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS", "/NP"],
        capture_output=True, text=True)
    # robocopy: 0~7 성공, 8+ 오류
    ok = p.returncode < 8
    dt = time.time() - t0
    sz = os.path.getsize(os.path.join(dst_dir, src_name)) if ok and os.path.isfile(os.path.join(dst_dir, src_name)) else 0
    print(f"    robocopy {src_name}: rc={p.returncode} {'OK' if ok else '실패'} "
          f"{sz/1e9:.2f}GB {dt:.1f}s ({sz/1e9/max(dt,0.01)*1000:.0f}MB/s)")
    if not ok: print(p.stdout, p.stderr)
    return ok

def main():
    print("="*70)
    print(f" 폰트 전용 빌드 (REUSE={REUSE})")
    print("="*70)
    for f in ("RES00.RDI","RES00.RDB","RES10.RDB"):
        if not os.path.isfile(f): raise SystemExit(f"원본 {f} 없음")
    for arc, ff in FONTS.items():
        if not os.path.isfile(ff): raise SystemExit(f"폰트 편집본 {ff} 없음")

    os.makedirs(OUT_DIR, exist_ok=True)
    dec, table, idx, rec_start = R.load_rdi("RES00.RDI")

    # 어떤 RDB 가 필요한지 결정
    needed = {}
    for arc, ff in FONTS.items():
        if arc not in idx: raise SystemExit(f"{arc} RDI에 없음")
        t = idx[arc]; loc = R.locate(t["stored"], t["flag"])
        needed.setdefault(loc[0], []).append((arc, ff, t, loc))

    # 1) 원본 → 출력 고속 복사 (또는 재사용)
    for rdb in needed:
        kp = os.path.join(OUT_DIR, rdb)
        if REUSE and os.path.isfile(kp) and os.path.getsize(kp) == os.path.getsize(rdb):
            print(f"  [재사용] {kp} (재복사 생략)")
        else:
            print(f"  [복사] {rdb} → {kp}")
            if not robocopy(rdb, OUT_DIR):
                raise SystemExit("복사 실패")

    # 2) 폰트 슬롯 제자리 패치
    report = []
    for rdb, items in needed.items():
        kp = os.path.join(OUT_DIR, rdb)
        with open(kp, "r+b") as fh:
            for arc, ff, t, loc in items:
                _, off0, is10 = loc
                flag = t["flag"]; key = R.file_key(arc)
                # 원본 슬롯 헤더 32B (권위 헤더)
                with open(rdb, "rb") as rf:
                    rf.seek(off0); head_raw = rf.read(32)
                header = bytearray(R.crypt(head_raw, key))
                body = open(ff, "rb").read()[32:]
                if flag > 0:
                    comp = zlib.compress(body, 9)
                    new_decsize = R.align_up(len(body), 4)
                    struct.pack_into("<I", header, 0x18, len(comp))
                else:
                    comp = body
                    new_decsize = R.align_up(32 + len(body), 4)
                    struct.pack_into("<I", header, 0x18, new_decsize)
                struct.pack_into("<I", header, 0x1C, off0 // R.SECTOR)  # 로컬섹터 불변
                need_phys = R.align_up(32 + len(comp), R.SECTOR)
                blob = bytearray(need_phys)
                blob[:32] = header; blob[32:32+len(comp)] = comp
                enc = R.crypt(bytes(blob), key)
                fh.seek(off0); fh.write(enc)
                # RDI 갱신 (제자리라 OFFSET 불변, DEC_SIZE만)
                rp = rec_start + t["i"]*9
                struct.pack_into("<I", dec, rp,   t["stored"])       # 불변
                struct.pack_into("<I", dec, rp+4, new_decsize)
                report.append((arc, rdb, off0, new_decsize, len(comp), key, kp, body, flag))
                print(f"  [제자리] {arc:22s} {rdb} off=0x{off0:x} decsize→{new_decsize} comp={len(comp)}")

    # 3) RDI 기록
    out_rdi = os.path.join(OUT_DIR, "RES00.RDI")
    R.save_rdi(dec, out_rdi)
    print(f"  RDI 기록: {out_rdi}")

    # 4) 검증 (해당 슬롯만 재독)
    if not NO_VERIFY:
        print("-"*70); print(" 검증(슬롯 재독)")
        ok = True
        for arc, rdb, off0, new_decsize, clen, key, kp, body, flag in report:
            with open(kp, "rb") as f:
                f.seek(off0); raw = f.read(new_decsize if flag==0 else R.align_up(32+clen,4))
            if len(raw) % 4: raw += b"\x00"*(4-len(raw)%4)
            d = R.crypt(raw, key)
            clen2 = struct.unpack_from("<I", d, 0x18)[0]
            chk = zlib.decompress(d[32:32+clen2]) if flag>0 else d[32:32+(new_decsize-32)]
            good = chk[:len(body)] == body and len(chk)==len(body)
            ok = ok and good
            print(f"   {arc:22s} {'OK' if good else '[불일치!]'}")
        if not ok: raise SystemExit("검증 실패 — 출력 사용 금지")
        print(" 검증: 전체 통과")

    print("="*70)
    print(" 완료. 아래를 romfs-.../cdvdroot/ 에 덮어쓰기:")
    for rdb in needed: print(f"   {os.path.join(OUT_DIR, rdb)}")
    print(f"   {out_rdi}")
    print(" exe(main)는 원본 사용(주입 안 함). 텍스트도 원문 그대로 → 폰트만 격리 테스트")
    print("="*70)

if __name__ == "__main__":
    main()
