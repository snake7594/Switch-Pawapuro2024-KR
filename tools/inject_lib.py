# -*- coding: utf-8 -*-
"""실황2024 번역 주입 공용 라이브러리
- CHK STRING 청크 재구성(문자열 교체, 가변길이) — 32바이트 슬롯헤더 보존
- 0x00-split(scan)/exe 오프셋 치환(길이 제약)
- 한국어→한자코드 인코더(테이블 구동)
"""
import struct, re

def u32(b, o): return struct.unpack_from("<I", b, o)[0]
def round_up(n, a): return (n + a - 1) // a * a

# ---------- CHK STRING 청크 재구성 ----------
def parse_string_list(b):
    """첫 STRING 청크의 문자열 리스트 반환(없으면 None)."""
    si = b.find(b"STRING")
    if si < 0: return None
    base = si + 0x10
    p0 = u32(b, base)
    if p0 < 4 or p0 % 4: return None
    N = p0 // 4
    out = []
    for k in range(N):
        off = u32(b, base + 4*k)
        s = base + off
        e = b.find(b"\x00", s)
        out.append(b[s:e])  # bytes (UTF-8)
    return out

def rebuild_string_chk(orig, new_strings_bytes):
    """orig(32바이트 슬롯헤더+CHK) + 새 문자열(bytes 리스트, 길이=원본 N) → 새 파일 bytes.
    STRING 청크를 재구성하고 size 필드(STRING size1/size2, CHK total)를 갱신.
    TABLE/CHUNKEND 등 STRING 이후 청크는 인덱스 참조이므로 그대로 보존."""
    si = orig.find(b"STRING")
    if si < 0: raise ValueError("STRING 청크 없음")
    base = si + 0x10
    old_size1 = u32(orig, si + 8)
    suffix = orig[si + old_size1:]            # TABLE + CHUNKEND (보존)
    N = len(new_strings_bytes)
    # 포인터 테이블 + 문자열 데이터(NUL종료)
    table_size = 4 * N
    offs = []
    off = table_size
    data = bytearray()
    for s in new_strings_bytes:
        offs.append(off)
        data += s + b"\x00"
        off += len(s) + 1
    ptr_bytes = b"".join(struct.pack("<I", o) for o in offs)
    body = ptr_bytes + bytes(data)            # base(0x70)부터
    chunk_unpadded = 0x10 + len(body)         # magic+size1+size2(0x10) + body
    # 항상 다음 16배수로 올림(이미 정렬돼도 16바이트 패딩 추가) — 실측 규칙
    new_size1 = (chunk_unpadded // 16 + 1) * 16
    pad = new_size1 - chunk_unpadded
    new_size2 = len(body) + 1                  # 실측: 포인터테이블+문자열데이터 + 1
    out = bytearray(orig[:base])              # [0 : base] (슬롯헤더+CHK헤더+HEADER+STRING매직+size)
    struct.pack_into("<I", out, si + 8, new_size1)
    struct.pack_into("<I", out, si + 12, new_size2)
    out += body
    if pad > 0:
        out += b"\xff" + b"\xcc" * (pad - 1)  # 패딩 패턴 ff cc cc...
    out += suffix
    # CHK total size @0x2C: 크기 변화량(델타)만큼만 갱신(파일별 절대의미 차이 회피)
    delta = new_size1 - old_size1
    struct.pack_into("<I", out, 0x2C, u32(orig, 0x2C) + delta)
    return bytes(out)

# ---------- 한국어→게임바이트 인코더 ----------
class Encoder:
    """한국어 음절 → 배정 한자코드(UTF-8). 비한글(ASCII/기호/제어태그/숫자/일본어)은 그대로 통과."""
    def __init__(self, table_path):
        self.m = self._load(table_path)
    @staticmethod
    def _load(p):
        b = open(p, "rb").read()
        if b[:2] == b"\xff\xfe":
            txt = b.decode("utf-16-le", "ignore")
        else:
            txt = b.decode("utf-8-sig", "ignore")
        m = {}
        for ln in txt.splitlines():
            ln = ln.replace("﻿", "")
            if ln.startswith("#") or "\t" not in ln: continue
            k, v = ln.split("\t", 1)
            if len(k) == 1 and v: m[k] = v[0]
        return m
    def encode(self, ko: str) -> bytes:
        out = []
        for ch in ko:
            out.append(self.m.get(ch, ch))   # 한글이면 한자로, 아니면 그대로
        return "".join(out).encode("utf-8")
    def covers(self, ko: str):
        """매핑 안 되는 한글 음절 목록(있으면 폰트 미지원)."""
        miss = []
        for ch in ko:
            if "가" <= ch <= "힣" and ch not in self.m:
                miss.append(ch)
        return miss

# ---------- 길이 제약 오프셋 치환(scan/exe) ----------
def patch_at_offset(buf: bytearray, offset: int, old_len: int, new_bytes: bytes):
    """offset의 문자열(old_len)을 new_bytes로 제자리 교체. **뒤따르는 NUL 슬랙까지 활용**.
    문자열 뒤 NUL런(T) → 최대 old_len+T-1 바이트까지 쓸 수 있음(NUL 종료 1개 유지).
    초과 시 UTF-8 경계로 잘라냄(반환=잘림 여부)."""
    T = 0
    k = offset + old_len
    while k < len(buf) and buf[k] == 0:
        T += 1; k += 1
    cap = old_len + T - 1 if T > 0 else old_len   # 종료 NUL 1개 유지
    region_end = offset + old_len + T
    truncated = False
    if len(new_bytes) > cap:
        new_bytes = new_bytes[:cap]
        # 유효 UTF-8이 될 때까지 뒤에서 제거(매달린 선두바이트 e6/e7/e8 포함).
        # 구버전은 연속바이트(0x80-0xBF)만 제거해 선두바이트가 남았고, 게임 렌더러가
        # 불완전 시퀀스로 NUL종료자를 삼켜 인접 ID문자열까지 읽는 누출 버그가 있었음.
        while new_bytes:
            try:
                new_bytes.decode("utf-8"); break
            except UnicodeDecodeError:
                new_bytes = new_bytes[:-1]
        truncated = True
    buf[offset:offset+len(new_bytes)] = new_bytes
    buf[offset+len(new_bytes):region_end] = b"\x00" * (region_end - offset - len(new_bytes))
    return truncated
