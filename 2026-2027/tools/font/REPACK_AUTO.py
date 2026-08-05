# -*- coding: utf-8 -*-
"""
실황파워풀프로야구 2024 — 자동 리팩 (파일 크기 변경 자동 대응)
=================================================================
편집한 CHK 를 RES00/RES10.RDB 에 자동으로 되돌려 넣는다.
크기가 커져서 원래 슬롯에 안 들어가면 RDB 끝에 '재배치(relocate)'하고
RDI 인덱스(OFFSET·DEC_SIZE)와 슬롯 헤더를 자동으로 갱신한다.

[입력]  repack_in/ 폴더에, 아카이브 이름 그대로(예: COMMON_2D.CHK, NAME_DIC.CHK)
        편집한 '복호화본'(= 32바이트 헤더 + 압축해제 본문, 즉 RES/복호화 추출물과 같은 형태)을 넣는다.
        (선택) repack_manifest.txt 로 임의 경로 매핑 가능:  아카이브이름 = 편집파일경로

[출력]  repack_out/ 폴더에 RES00.RDB / RES10.RDB / RES00.RDI 를 배포용 이름 그대로 생성.
        (그대로 romfs-.../cdvdroot/ 에 복사해 덮어쓰기. 기존 -K 작업본은 건드리지 않음)

[검증된 포맷]  (READ-ONLY 실측으로 확인)
 - 암복호화: 파일별 키 XOR 스트림, 복호=암호 동일 연산(involution). byte-exact.
 - 슬롯 = 32바이트 헤더 + zlib(deflate, level 9) 압축본 (+뒤쪽 무시되는 여분)
 - 헤더 32B: [0x00] 파일명 ascii, [0x18] u32 = 압축크기, [0x1C] u32 = 로컬 섹터 오프셋
 - RDI(OFFSET) = 로컬 섹터값(바이트오프셋/0x200), RES10 은 +0x1000000.  flag 0/0x20 만 추출 대상.
 - RDI(DEC_SIZE) = '압축 해제 크기'. 게임은 이 길이만큼 슬롯을 읽어 복호화 후 zlib 해제한다.
"""
import sys, os, zlib, shutil, struct
from array import array

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

# ---------------- 설정 ----------------
INPUT_DIR      = "repack_in"           # 편집한 복호화본을 넣는 폴더(아카이브 이름 그대로)
MANIFEST       = "repack_manifest.txt" # (선택) '아카이브이름 = 경로' 매핑
OUT_DIR        = "repack_out"          # 출력 폴더 → repack_out/RES00.RDB · RES10.RDB · RES00.RDI (배포용 이름)
SECTOR         = 0x200                  # 오프셋 정렬 단위
ZLEVEL         = 9                      # 원본과 동일(검증됨)
FRESH          = True                   # True: 매번 원본에서 -K 새로 복사(결정적). False(--reuse): 기존 -K 재사용+항상 끝에 추가
VERIFY         = True                   # 기록 후 -K 에서 다시 읽어 본문 일치 검증
# 명령줄: --reuse(빠른 반복, 항상 재배치) / --no-verify
for a in sys.argv[1:]:
    if a == "--reuse":      FRESH = False
    elif a == "--no-verify":VERIFY = False
    elif a == "--fresh":    FRESH = True

# ---------------- 키/암복호화 (원본 스크립트와 동일) ----------------
def GenerateKey(string):
    table = [5,6,4,5,6,5,4,5,5,6,6,5,6,4,6,4]
    root = ("data:/cdvdroot/" + string).encode("ascii")
    X18=0x1A7B9611A7B9611B; X8=-1; W16=0x5C; W0=0x1D; W10=0; W9=0
    while True:
        W12=root[X8]; W11=(W12-0x61)&0xFF
        W11=(W12-0x20) if W11<0x1A else W12
        if W12==0x2F: break
        W12=W11&0xFF
        if W12==0x5C: break
        W11=W12; W10+=1; W9=(W10*W11)+W9; X8-=1
        if abs(X8)==len(root): break
    iter=W10
    root=("/"+string).encode("ascii")
    W12=root[1]; W9+=W10; W11=0; W10=2; W8=W9
    for i in range(iter):
        W14=(W12-0x61)&0xFF; W13=W12&0xFF
        if W14<0x1A: W12-=0x20
        if W13==0x2F: W12=W16
        W12=(W12&0xFF)-0x30; W12<<=W11; W8=(W8+W12)&0xFFFFFFFF
        if W10==len(root): break
        W12=(W9&0xF)&0xFFFFFFFF; W9+=1; W12=table[W12]
        W11=(W11+W12)&0xFFFFFFFF
        W12=(W11*X18)>>64; W13=W11-W12; W12+=(W13>>1); W12=(W12>>4)&0xFFFFFFFF
        W11=(W11-(W12*W0))&0xFFFFFFFF
        W12=root[W10]; W10+=1
    return W8

def Keygen(key):
    T=[0]*64; itr1=0; w27=0xb1aef645
    while True:
        w13=0; itr2=0
        while True:
            w14=(key+(key<<2))&0xFFFFFFFF
            flag=(w13==0); w15=w13-1
            w14=(w14+w27)&0xFFFFFFFF; w14=(w14>>1)&0xFFFFFFFF
            if flag: key=w14; w12=w14
            w14=T[itr2]; w13=w12&1; w12//=2
            w13=(w13<<itr1)&0xFFFFFFFF; w13=(w13|w14)&0xFFFFFFFF
            T[itr2]=w13; itr2+=1
            w13=30 if flag else w15
            if itr2==64: break
        itr1+=1
        if itr1==32: break
    return T

def crypt(data, key, nwords=None):
    """복호화/암호화 동일 연산. data: bytes(4의 배수). nwords 지정 시 앞부분만."""
    if len(data) % 4: raise ValueError("데이터 길이가 4의 배수가 아님")
    total = len(data)//4
    n = total if nwords is None else min(nwords, total)
    KT = Keygen(key)
    out = bytearray(n*4)
    mv = memoryview(data)
    for x in range(n):
        KT[x % 64] ^= KT[(x+3) % 64]
        w = int.from_bytes(mv[x*4:x*4+4], "little")
        out[x*4:x*4+4] = (w ^ KT[(x+1) % 64]).to_bytes(4, "little")
    return bytes(out)

def align_up(v, a): return (v + a - 1) // a * a

RDI_KEY = GenerateKey("RES00.RDI")
def file_key(name): return RDI_KEY ^ GenerateKey(name)

# ---------------- RDI 적재/파싱 ----------------
def load_rdi(path):
    with open(path, "rb") as f: raw = f.read()
    w = array('I'); w.frombytes(raw)
    dec = bytearray(crypt(raw, RDI_KEY))
    if dec[:4] != b"RDI2": raise SystemExit("RDI 매직 불일치")
    file_count = struct.unpack_from("<I", dec, 0x10)[0]
    flag3      = struct.unpack_from("<I", dec, 0x0C)[0]
    lte        = struct.unpack_from("<I", dec, 0x24)[0]
    p = 0x30 + 8 + (8 if flag3 == 2 else 0)
    name_off = list(struct.unpack_from("<%dI" % file_count, dec, p)); p += 4*file_count
    rec_start = p
    table = []
    for i in range(file_count):
        off, ds = struct.unpack_from("<II", dec, p); fl = dec[p+8]; p += 9
        table.append({"i": i, "stored": off, "DEC_SIZE": ds, "flag": fl})
    p += 8*lte
    name_base = p
    for i in range(file_count):
        s = dec.index(b"\x00", name_base+name_off[i])
        table[i]["name"] = dec[name_base+name_off[i] : s].decode("ascii")
    idx = {t["name"]: t for t in table}
    return dec, table, idx, rec_start

def save_rdi(dec, out_path):
    enc = crypt(bytes(dec), RDI_KEY)
    with open(out_path, "wb") as f: f.write(enc)

# real(byte) offset 및 소속 RDB
def locate(stored, flag):
    if flag not in (0, 0x20): return None  # ID 타입 (추출/주입 불가)
    real = stored * SECTOR
    if real >= 0x200000000:
        return ("RES10.RDB", real - 0x200000000, True)   # (원본명, 로컬바이트, is_res10)
    return ("RES00.RDB", real, False)

def stored_from_local(local_byte, is_res10):
    sect = local_byte // SECTOR
    return sect + (0x1000000 if is_res10 else 0), sect

# ---------------- 입력 매핑 수집 ----------------
def collect_inputs():
    """반환: dict 아카이브이름 -> 편집파일경로"""
    jobs = {}
    if os.path.isfile(MANIFEST):
        for line in open(MANIFEST, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" not in line: continue
            k, v = line.split("=", 1)
            jobs[k.strip()] = v.strip()
    if os.path.isdir(INPUT_DIR):
        for fn in sorted(os.listdir(INPUT_DIR)):
            full = os.path.join(INPUT_DIR, fn)
            if os.path.isfile(full):
                jobs.setdefault(fn, full)   # 매니페스트 우선
    return jobs

# ---------------- 메인 ----------------
def main():
    print("="*70)
    print(" 자동 리팩 시작 (FRESH=%s, VERIFY=%s)" % (FRESH, VERIFY))
    print("="*70)
    if not os.path.isfile("RES00.RDI"):
        raise SystemExit("RES00.RDI 가 현재 폴더에 없습니다.")
    jobs = collect_inputs()
    if not jobs:
        raise SystemExit("입력이 없습니다. '%s/' 폴더에 편집한 CHK(아카이브 이름)를 넣으세요." % INPUT_DIR)

    dec, table, idx, rec_start = load_rdi("RES00.RDI")
    print("RDI 적재: 항목 %d개, 레코드테이블 0x%X" % (len(table), rec_start))

    # 각 RDB 별 정렬된 오프셋(원본 레이아웃) — 제자리 교체 시 다음 파일까지의 빈공간 계산용
    laid = {"RES00.RDB": [], "RES10.RDB": []}
    for t in table:
        loc = locate(t["stored"], t["flag"])
        if loc: laid[loc[0]].append(loc[1])
    for k in laid: laid[k].sort()
    orig_size = {}
    for k in ("RES00.RDB", "RES10.RDB"):
        orig_size[k] = os.path.getsize(k) if os.path.isfile(k) else 0

    def gap_to_next(rdb, local_byte):
        arr = laid[rdb]
        import bisect
        j = bisect.bisect_right(arr, local_byte)
        nxt = arr[j] if j < len(arr) else orig_size[rdb]
        return nxt - local_byte

    # 필요한 RDB 만 -K 준비
    needed = set()
    valid_jobs = {}
    for name, path in jobs.items():
        if name not in idx:
            print("  [건너뜀] '%s' 은 RDI 에 없음" % name); continue
        t = idx[name]
        loc = locate(t["stored"], t["flag"])
        if loc is None:
            print("  [건너뜀] '%s' 은 ID 타입(OFFSET 없음) — RDB 주입 불가" % name); continue
        needed.add(loc[0]); valid_jobs[name] = (path, t, loc)
    if not valid_jobs: raise SystemExit("처리할 유효한 입력이 없습니다.")

    os.makedirs(OUT_DIR, exist_ok=True)
    kpath = {}
    for rdb in needed:
        kp = os.path.join(OUT_DIR, rdb)
        kpath[rdb] = kp
        if FRESH or not os.path.isfile(kp):
            if not os.path.isfile(rdb): raise SystemExit("원본 %s 가 없습니다." % rdb)
            print("  출력 사본 생성: %s → %s  (%.2f GB, 잠시 대기)" % (rdb, kp, os.path.getsize(rdb)/1e9))
            shutil.copy2(rdb, kp)
        else:
            print("  출력 재사용(append): %s" % kp)

    # 추가(append) 커서: 기존 -K 끝(섹터정렬)
    cursor = {rdb: align_up(os.path.getsize(kpath[rdb]), SECTOR) for rdb in needed}

    report = []
    fh = {}  # 열린 -K 핸들
    try:
        for rdb in needed:
            fh[rdb] = open(kpath[rdb], "r+b")

        for name, (path, t, loc) in valid_jobs.items():
            rdb, off0_local, is_res10 = loc
            flag = t["flag"]; orig_decsize = t["DEC_SIZE"]
            key = file_key(name)

            # 1) 원본 슬롯 헤더 32B 만 복호화해 권위있는 헤더 확보
            with open(rdb, "rb") as rf:
                rf.seek(off0_local); head_raw = rf.read(32)
            header = bytearray(crypt(head_raw, key))   # 32B
            # 이름 sanity
            edited = open(path, "rb").read()
            if len(edited) < 32:
                print("  [경고] %s: 너무 짧음, 건너뜀" % name); continue
            if bytes(edited[:4]) != bytes(header[:4]):
                print("  [경고] %s: 편집파일 헤더(%r)가 아카이브 헤더(%r)와 다름 — 그래도 본문만 사용"
                      % (name, bytes(edited[:4]), bytes(header[:4])))
            new_body = edited[32:]                     # 압축 해제 본문(편집본)

            # 2) 압축 + DEC_SIZE 계산
            if flag > 0:
                comp = zlib.compress(new_body, ZLEVEL)
                new_decsize = align_up(len(new_body), 4)        # 압축: DEC_SIZE=압축해제 크기
                struct.pack_into("<I", header, 0x18, len(comp)) # 헤더[0x18]=압축크기
            else:
                comp = new_body                                 # flag 0: 비압축 그대로
                new_decsize = align_up(32 + len(new_body), 4)   # 비압축: DEC_SIZE=슬롯길이(헤더32+본문)
                struct.pack_into("<I", header, 0x18, new_decsize)

            # 3) 제자리 교체 가능? (FRESH 모드 + 압축본이 다음 파일까지 빈공간에 들어감)
            need_phys = align_up(32 + len(comp), 4)
            inplace = FRESH and (need_phys <= gap_to_next(rdb, off0_local))

            if inplace:
                # 헤더[0x1C]=로컬 섹터(불변), 슬롯 앞부분만 덮어씀
                struct.pack_into("<I", header, 0x1C, off0_local // SECTOR)
                blob = bytearray(need_phys)
                blob[:32] = header
                blob[32:32+len(comp)] = comp
                enc = crypt(bytes(blob), key)
                fh[rdb].seek(off0_local); fh[rdb].write(enc)
                new_stored = t["stored"]               # 불변
                where = "제자리"
                new_local = off0_local
            else:
                # 재배치: -K 끝(섹터정렬)에 자족적 슬롯(헤더+압축+0패딩) 기록
                new_local = cursor[rdb]
                new_stored, sect = stored_from_local(new_local, is_res10)
                struct.pack_into("<I", header, 0x1C, sect)        # 헤더[0x1C]=새 로컬 섹터
                phys = align_up(max(new_decsize, 32 + len(comp)), SECTOR)
                blob = bytearray(phys)
                blob[:32] = header
                blob[32:32+len(comp)] = comp
                enc = crypt(bytes(blob), key)
                fh[rdb].seek(new_local); fh[rdb].write(enc)
                cursor[rdb] = new_local + phys
                where = "재배치"

            # 4) RDI 레코드 갱신 (OFFSET, DEC_SIZE)
            rp = rec_start + t["i"]*9
            struct.pack_into("<I", dec, rp,   new_stored)
            struct.pack_into("<I", dec, rp+4, new_decsize)
            # flag 불변

            report.append({
                "name": name, "rdb": rdb, "where": where,
                "orig_decsize": orig_decsize, "new_decsize": new_decsize,
                "comp": len(comp), "off": new_local, "stored": new_stored,
                "key": key, "kpath": kpath[rdb], "new_body": new_body, "flag": flag,
            })
            print("  [%s] %-28s %s  decsize %d→%d  comp %d  off 0x%X"
                  % (where, name, rdb, orig_decsize, new_decsize, len(comp), new_local))
    finally:
        for f in fh.values(): f.close()

    # 5) RDI 기록
    out_rdi = os.path.join(OUT_DIR, "RES00.RDI")
    save_rdi(dec, out_rdi)
    print("RDI 기록: %s" % out_rdi)

    # 6) 검증: -K 에서 다시 읽어 본문 일치 확인
    if VERIFY:
        print("-"*70); print(" 검증 (기록본 재독)")
        ok = True
        for r in report:
            with open(r["kpath"], "rb") as f:
                f.seek(r["off"]); raw = f.read(r["new_decsize"])
            if len(raw) % 4: raw += b"\x00" * (4 - len(raw) % 4)
            d = crypt(raw, r["key"])
            comp_len = struct.unpack_from("<I", d, 0x18)[0]
            body_chk = zlib.decompress(d[32:32+comp_len]) if r["flag"] > 0 else d[32:32+ (r["new_decsize"]-32)]
            good = body_chk[:len(r["new_body"])] == r["new_body"] and len(body_chk) == len(r["new_body"])
            ok = ok and good
            print("   %-28s %s" % (r["name"], "OK" if good else "[불일치!]"))
        print(" 검증 결과:", "전체 통과 (OK)" if ok else "[실패 항목 있음]")
        if not ok:
            raise SystemExit("검증 실패 — 출력 파일을 사용하지 마세요.")

    # 7) 요약
    print("="*70)
    print(" 완료. 아래 출력물을 romfs-.../cdvdroot/ 에 그대로 복사해 덮어쓰면 됩니다:")
    for rdb in needed:
        print("   %s" % kpath[rdb])
    print("   %s" % out_rdi)
    print(" (RES00.RDI 는 항상 새로 만들어지므로 RES00/RES10 양쪽 다 쓸 때도 이 RDI 하나만 배포)")
    rel = [r for r in report if r["where"] == "재배치"]
    if rel:
        print(" 재배치된 파일 %d개 (해당 RDB 가 그만큼 커짐). 반복 실행 시 --reuse 로 재복사 생략 가능." % len(rel))
    print("="*70)

if __name__ == "__main__":
    main()
