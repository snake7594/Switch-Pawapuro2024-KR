# -*- coding: utf-8 -*-
"""NSO 헤더 감사: 원본/구수동본/신주입본의 플래그·섹션·해시 검증.
   NSO0: 0x0C=flags(bit0-2 압축, bit3-5 해시검증), 세그헤더 0x10/0x20/0x30,
   압축크기 0x60/0x64/0x68, SHA256 해시 0xA0(text)/0xC0(ro)/0xE0(data)."""
import sys, struct, hashlib
sys.stdout.reconfigure(encoding='utf-8')
import os
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본+데이터). 미지정 시 현재 디렉터리 사용

def parse(path):
    b=open(path,'rb').read()
    flags=struct.unpack_from('<I',b,0x0C)[0]
    segs={}
    for name,off in (('text',0x10),('ro',0x20),('data',0x30)):
        fo,mo,sz=struct.unpack_from('<III',b,off)
        segs[name]=dict(fo=fo,mo=mo,sz=sz)
    csz=struct.unpack_from('<III',b,0x60)
    hashes={'text':b[0xA0:0xC0],'ro':b[0xC0:0xE0],'data':b[0xE0:0x100]}
    return b,flags,segs,csz,hashes

FILES={'원본':'main', '구수동본(8/12)':'!exefs-작업/main', '신주입본':'inject_out/main'}
parsed={}
for label,p in FILES.items():
    b,flags,segs,csz,hashes=parse(p)
    parsed[label]=(b,flags,segs,csz,hashes)
    print(f"===== {label} ({p}) =====")
    print(f"  flags=0x{flags:02x}  압축[text={flags&1},ro={(flags>>1)&1},data={(flags>>2)&1}]  해시검증[text={(flags>>3)&1},ro={(flags>>4)&1},data={(flags>>5)&1}]")
    for n in ('text','ro','data'):
        s=segs[n]
        print(f"  {n:5s}: fileoff=0x{s['fo']:x} memoff=0x{s['mo']:x} size=0x{s['sz']:x}")
    print(f"  압축크기: {csz}")
    for n in ('text','ro','data'):
        print(f"  {n:5s} hash: {hashes[n].hex()[:32]}...")
    print()

# 해시 실검증 (비압축 가정: 파일의 [fo:fo+sz]가 곧 섹션)
print("===== 섹션 해시 실검증 =====")
for label in FILES:
    b,flags,segs,csz,hashes=parsed[label]
    print(f"  [{label}]")
    for n in ('text','ro','data'):
        s=segs[n]
        comp=(flags>>('text ro data'.split().index(n)))&1
        sec=b[s['fo']:s['fo']+s['sz']]
        actual=hashlib.sha256(sec).digest()
        ok=actual==hashes[n]
        print(f"    {n:5s}: 헤더해시{'==' if ok else '!='}실제  (압축플래그={comp})")

# 신주입본 vs 원본: 섹션별 변경 바이트 수
print("\n===== 신주입본 vs 원본 변경 분포 =====")
bo=parsed['원본'][0]; bn=parsed['신주입본'][0]
segs=parsed['원본'][2]
import numpy as np
ao=np.frombuffer(bo,dtype=np.uint8); an=np.frombuffer(bn,dtype=np.uint8)
if len(ao)==len(an):
    diff=np.nonzero(ao!=an)[0]
    print(f"  총 변경 바이트: {len(diff):,}")
    for n in ('text','ro','data'):
        s=segs[n]
        cnt=((diff>=s['fo'])&(diff<s['fo']+s['sz'])).sum()
        print(f"  {n:5s} 구간 [0x{s['fo']:x},0x{s['fo']+s['sz']:x}): {cnt:,}바이트 변경")
    hdr=((diff<0x100)).sum()
    print(f"  헤더(0x0~0x100): {hdr}바이트 변경")
