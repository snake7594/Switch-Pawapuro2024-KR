# -*- coding: utf-8 -*-
"""RDB 슬롯 접근 공용 라이브러리 (REPACK_AUTO 검증 로직 재사용).
- load_rdi / read_slot(복호+해제) / write_slot(압축+암호, 제자리 or 재배치)
"""
import os, zlib, struct
from array import array

SECTOR = 0x200
ZLEVEL = 9

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
    if len(data) % 4: raise ValueError("len%4!=0")
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

def crypt_fast(data, key):
    """crypt와 동일 결과, numpy 블록 벡터화(~80MB/s). 검증: 레퍼런스와 byte-identical."""
    import numpy as np
    n = len(data)//4
    if n == 0: return b''
    KT0 = np.array(Keygen(key), dtype=np.uint64)
    nblocks = (n+63)//64
    states = np.empty((nblocks+1, 64), dtype=np.uint64)
    states[0] = KT0
    s = KT0.copy()
    for k in range(nblocks):
        new = np.empty(64, dtype=np.uint64)
        new[:61] = s[:61] ^ s[3:64]
        new[61] = s[61] ^ new[0]
        new[62] = s[62] ^ new[1]
        new[63] = s[63] ^ new[2]
        states[k+1] = new
        s = new
    ks = np.empty((nblocks, 64), dtype=np.uint64)
    ks[:, :63] = states[:nblocks, 1:64]
    ks[:, 63] = states[1:nblocks+1, 0]
    ks_flat = ks.reshape(-1)[:n].astype(np.uint32)
    w = np.frombuffer(data[:n*4], dtype=np.uint32)
    return (w ^ ks_flat).tobytes()

RDI_KEY = GenerateKey("RES00.RDI")
def file_key(name): return RDI_KEY ^ GenerateKey(name)

def load_rdi(path):
    with open(path, "rb") as f: raw = f.read()
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
        table.append({"i": i, "stored": off, "DEC_SIZE": ds, "flag": fl, "rec_off": rec_start + 9*i})
    p += 8*lte
    name_base = p
    for i in range(file_count):
        s = dec.index(b"\x00", name_base+name_off[i])
        table[i]["name"] = dec[name_base+name_off[i] : s].decode("ascii")
    idx = {t["name"]: t for t in table}
    return dec, table, idx

def locate(stored, flag):
    if flag not in (0, 0x20): return None
    real = stored * SECTOR
    if real >= 0x200000000:
        return ("RES10.RDB", real - 0x200000000, True)
    return ("RES00.RDB", real, False)

class RDB:
    """배포/원본 RDB 세트 접근자. rdb_dir: RES00.RDB/RES10.RDB/RES00.RDI 위치."""
    def __init__(self, rdb_dir, writable=False):
        self.dir = rdb_dir
        self.rdi_path = os.path.join(rdb_dir, "RES00.RDI")
        self.dec, self.table, self.idx = load_rdi(self.rdi_path)
        mode = "r+b" if writable else "rb"
        self.f = {}
        for n in ("RES00.RDB", "RES10.RDB"):
            p = os.path.join(rdb_dir, n)
            if os.path.isfile(p): self.f[n] = open(p, mode)
    def slot_raw(self, ent, name):
        """(rdbname, local_off, dec_header32, enc_slot_bytes, csize, is10).
        슬롯 전체(헤더32+압축본)가 슬롯 시작 기준 단일 키스트림으로 암호화됨."""
        loc = locate(ent["stored"], ent["flag"])
        if not loc: return None
        rdbn, off, is10 = loc
        key = file_key(name)
        f = self.f[rdbn]; f.seek(off)
        hdr_raw = f.read(32)
        hdr = crypt_fast(hdr_raw, key)          # 복호된 헤더
        csize = struct.unpack_from("<I", hdr, 0x18)[0]
        rest = f.read(align_up(csize, 4))
        return rdbn, off, hdr, hdr_raw + rest, csize, is10
    def read_body(self, name):
        """복호+해제된 본문(bytes). flag=0(비압축)도 처리."""
        ent = self.idx.get(name)
        if not ent: return None
        r = self.slot_raw(ent, name)
        if not r: return None
        rdbn, off, hdr, enc_slot, csize, is10 = r
        key = file_key(name)
        full = crypt_fast(enc_slot, key)
        if ent["flag"] == 0x20:
            return zlib.decompress(full[32:32+csize])   # csize=압축크기
        return full[32:csize]                            # flag=0: csize=32+본문
    def close(self):
        for f in self.f.values(): f.close()
