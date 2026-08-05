import sys
import os
import zlib
import pandas as pd
from array import array
import shutil

def readString(myfile):
    chars = []
    while True:
        c = myfile.read(1)
        if c == b'\x00':
            return b"".join(chars).decode("ascii")
        chars.append(c)

def GenerateKey(string):
    table = [5, 6, 4, 5, 6, 5, 4, 5, 5, 6, 6, 5, 6, 4, 6, 4]
    root = "data:/cdvdroot/"
    filename = string
    root += filename
    root = root.encode("ascii")
    strlen = len(root)
    X18 = 0x1A7B9611A7B9611B
    X8 = -1
    W16 = 0x5C
    W0 = 0x1D
    W10 = 0
    W9 = 0
    while True:
        W12 = root[X8]
        W11 = W12 - 0x61
        W11 &= 0xFF
        if W11 < 0x1A:
            W11 = W12 - 0x20
        else:
            W11 = W12
        if W12 == 0x2F:
            break
        W12 = W11 & 0xFF
        if W12 == 0x5C:
            break
        W11 = W12
        W10 += 1
        W9 = (W10 * W11) + W9
        X8 -= 1
        if abs(X8) == len(root):
            break
    iter = W10
    root = "/" + filename
    root = root.encode("ascii")
    W12 = root[1]
    W9 += W10
    W11 = 0
    W10 = 2
    W8 = W9
    for i in range(iter):
        W14 = W12 - 0x61
        W13 = W12 & 0xFF
        W14 &= 0xFF
        if W14 < 0x1A:
            W12 -= 0x20
        if W13 == 0x2F:
            W12 = W16
        W12 &= 0xFF
        W12 -= 0x30
        W12 <<= W11
        W8 += W12
        W8 &= 0xFFFFFFFF
        if W10 == len(root):
            break
        W12 = W9 & 0xF
        W12 &= 0xFFFFFFFF
        W9 += 1
        W12 = table[W12]
        W11 += W12
        W11 &= 0xFFFFFFFF
        W12 = W11 * X18
        W12 >>= 64
        W13 = W11 - W12
        W12 += (W13 >> 1)
        W12 >>= 4
        W12 &= 0xFFFFFFFF
        W11 = W11 - (W12 * W0)
        W11 &= 0xFFFFFFFF
        W12 = root[W10]
        W10 += 1
    return W8

def Keygen(key):
    RDI_TABLE = [0] * 64
    itr1 = 0
    w27 = 0xb1aef645
    while True:
        w13 = 0
        itr2 = 0
        while True:
            w14 = key + (key << 2)
            w14 &= 0xFFFFFFFF
            flag = w13 == 0
            w15 = w13 - 1
            w14 = w14 + w27
            w14 &= 0xFFFFFFFF
            w14 >>= 1
            w14 &= 0xFFFFFFFF
            if flag:
                key = w14
                w12 = w14
            w14 = RDI_TABLE[itr2]
            w13 = w12 & 1
            w12 = w12 // 2
            w13 <<= itr1
            w13 &= 0xFFFFFFFF
            w13 |= w14
            w13 &= 0xFFFFFFFF
            RDI_TABLE[itr2] = w13
            itr2 += 1
            if flag:
                w13 = 30
            else:
                w13 = w15
            if itr2 == 64:
                break
        itr1 += 1
        if itr1 == 32:
            break
    return RDI_TABLE

# Decrypt RDI
RDI_KEY = GenerateKey("RES00.RDI")
KEYTABLE = Keygen(RDI_KEY)
with open("RES00.RDI", "rb") as RDI_FILE:
    RDI_FILE.seek(0, 2)
    filesize = RDI_FILE.tell()
    RDI_FILE.seek(0)
    RDI_INTS = []
    while RDI_FILE.tell() < filesize:
        RDI_INTS.append(int.from_bytes(RDI_FILE.read(4), "little"))

RDI_OUTPUT = []
for i in range(len(RDI_INTS)):
    KEYTABLE[i % 64] = KEYTABLE[i % 64] ^ KEYTABLE[(i+3) % 64]
    RDI_OUTPUT.append((RDI_INTS[i] ^ KEYTABLE[(i+1) % 64]).to_bytes(4, "little"))

with open("DEC_RES00.RDI", "wb") as file:
    file.write(b"".join(RDI_OUTPUT))

os.makedirs("RES", exist_ok=True)

with open("DEC_RES00.RDI", "rb") as file:
    if file.read(4) != b"RDI2":
        print("WRONG MAGIC!")
        sys.exit()
    file.seek(4)
    flag1 = int.from_bytes(file.read(2), "little")
    assert(flag1 == 1)
    flag2 = int.from_bytes(file.read(2), "little")
    assert(flag2 in [0, 1])
    if os.path.getsize("DEC_RES00.RDI") != int.from_bytes(file.read(4), "little"):
        print("SIZE CHECK FAILED!")
        sys.exit()
    flag3 = int.from_bytes(file.read(4), "little")
    if flag3 == 2:
        print("Detected index with patch, patch RES11.RDB not supported...")
    file_count = int.from_bytes(file.read(4), "little")
    file_count2 = int.from_bytes(file.read(4), "little")
    assert(file_count == file_count2)
    flag4 = int.from_bytes(file.read(4), "little")
    assert(flag4 == 0)
    flag5 = int.from_bytes(file.read(4), "little")
    assert(flag5 == 2)
    flag6 = int.from_bytes(file.read(4), "little")
    assert(flag6 == 0x10)
    last_table_entries = int.from_bytes(file.read(4), "little")
    flag8 = int.from_bytes(file.read(8), "little")
    assert(flag8 == 0)
    some_offset = int.from_bytes(file.read(4), "little")
    some_number = int.from_bytes(file.read(4), "little")
    if flag3 == 2:
        some_offset2 = int.from_bytes(file.read(4), "little")
        some_number2 = int.from_bytes(file.read(4), "little")

    TABLE = []
    for i in range(file_count):
        entry = {}
        entry["NAME_OFFSET"] = int.from_bytes(file.read(4), "little")
        TABLE.append(entry)
    flags = []
    for i in range(file_count):
        TABLE[i]["OFFSET"] = int.from_bytes(file.read(4), "little")
        TABLE[i]["DEC_SIZE"] = int.from_bytes(file.read(4), "little")
        TABLE[i]["flag"] = int.from_bytes(file.read(1), "little")
        if TABLE[i]["flag"] not in flags:
            flags.append(TABLE[i]["flag"])
        if TABLE[i]["flag"] in [0x20, 0]:
            TABLE[i]["OFFSET"] = TABLE[i]["OFFSET"] * 0x200
        else:
            TABLE[i]["ID"] = TABLE[i]["OFFSET"]
            TABLE[i].pop("OFFSET")
    for i in range(last_table_entries):
        file.read(8)  # Skip patch info

    base = file.tell()
    for i in range(file_count):
        file.seek(base + TABLE[i]["NAME_OFFSET"])
        TABLE[i]["FILENAME"] = readString(file)
        TABLE[i].pop("NAME_OFFSET")

do_excel = input("엑셀 파일(RDI_table.xlsx)로 내보내시겠습니까? (Y/N): ").strip().lower()
if do_excel == "y":
    excel_rows = []
    for entry in TABLE:
        row = {
            "FILENAME": entry["FILENAME"],
            "DEC_SIZE": "0x%X" % entry["DEC_SIZE"],
            "flag": "0x%X" % entry["flag"],
        }
        if "OFFSET" in entry:
            row["OFFSET"] = "0x%X" % entry["OFFSET"]
        elif "ID" in entry:
            row["ID"] = "0x%X" % entry["ID"]
        excel_rows.append(row)
    df = pd.DataFrame(excel_rows)
    df.to_excel("RDI_table.xlsx", index=False)
    print("Excel export completed: RDI_table.xlsx")
else:
    print("엑셀 내보내기 건너뜀.")

# ------ 언팩 기능 ------
do_unpack = input("특정 파일 언팩을 하시겠습니까? (Y/N): ").strip().lower()
if do_unpack == "y":
    filename_to_unpack = input("Enter the filename to unpack: ").strip()
    entry = next((e for e in TABLE if e["FILENAME"] == filename_to_unpack), None)
    if entry is None:
        print(f"File '{filename_to_unpack}' not found in the archive.")
    else:
        def get_rdb_source_and_offset(offset):
            if offset >= 0x200000000:
                return "RES10.RDB", offset - 0x200000000
            else:
                return "RES00.RDB", offset

        if "OFFSET" in entry:
            source_rdb, real_offset = get_rdb_source_and_offset(entry["OFFSET"])
        else:
            source_rdb, real_offset = None, None

        if source_rdb is None:
            print(f"{entry['FILENAME']} (ID 타입, OFFSET 없음) : RDB 추출 불가")
        else:
            with open(source_rdb, "rb") as file:
                file.seek(0, 2)
                RDBfilesize = file.tell()
                i = TABLE.index(entry)
                if entry["flag"] > 0x20:
                    print("%d/%d: %s, unsupported flag. Ignoring..." % (i+1, len(TABLE), entry["FILENAME"]))
                else:
                    print("%d/%d: %s (from %s, offset 0x%X)" % (i+1, len(TABLE), entry["FILENAME"], source_rdb, real_offset))
                    if real_offset > RDBfilesize:
                        print("READ OFFSET IS WRONG: %s, IGNORING..." % hex(real_offset))
                    elif real_offset + entry["DEC_SIZE"] > RDBfilesize:
                        print("READ OFFSET or SIZE IS WRONG: %s, IGNORING..." % hex(real_offset))
                    else:
                        file.seek(real_offset)
                        DATA = array('I')
                        DATA.fromfile(file, entry["DEC_SIZE"] // 4)

                        raw_dir = os.path.join("RES", "암호화_원본")
                        os.makedirs(raw_dir, exist_ok=True)
                        raw_path = os.path.join(raw_dir, entry["FILENAME"])
                        with open(raw_path, "wb") as raw_file:
                            for x in range(len(DATA)):
                                raw_file.write(DATA[x].to_bytes(4, "little"))
                        print(f"[중간파일] 암호화 원본 저장됨: {raw_path}")

                        KEYTABLE = Keygen(RDI_KEY ^ GenerateKey(entry["FILENAME"]))
                        RDI_OUTPUT = []
                        for x in range(len(DATA)):
                            KEYTABLE[x % 64] = KEYTABLE[x % 64] ^ KEYTABLE[(x+3) % 64]
                            RDI_OUTPUT.append((DATA[x] ^ KEYTABLE[(x+1) % 64]).to_bytes(4, "little"))
                        decrypt_dir = os.path.join("RES", "디크립트_압축본")
                        os.makedirs(decrypt_dir, exist_ok=True)
                        decrypt_path = os.path.join(decrypt_dir, entry["FILENAME"])
                        with open(decrypt_path, "wb") as dfile:
                            dfile.write(b"".join(RDI_OUTPUT))
                        print(f"[중간파일] 디크립트(압축전) 저장됨: {decrypt_path}")

                        filesize = int.from_bytes(RDI_OUTPUT[6], "little")
                        result_dir = os.path.join("RES", "복호화")
                        os.makedirs(result_dir, exist_ok=True)
                        result_path = os.path.join(result_dir, entry["FILENAME"])
                        if entry["flag"] > 0:
                            try:
                                dec_data = zlib.decompress(b"".join(RDI_OUTPUT[8:]))
                            except:
                                print("Failed decompressing data! Dumping raw file to 'FAILED' folder. Ignoring...")
                                os.makedirs("FAILED/RAW", exist_ok=True)
                                os.makedirs("FAILED/DECRYPTED", exist_ok=True)
                                with open("FAILED/DECRYPTED/%s" % entry["FILENAME"], "wb") as new_file:
                                    new_file.write(b"".join(RDI_OUTPUT))
                                with open("FAILED/RAW/%s" % entry["FILENAME"], "wb") as new_file:
                                    for x in range(len(DATA)):
                                        new_file.write(DATA[x].to_bytes(4, "little"))
                            else:
                                with open(result_path, "wb") as new_file:
                                    new_file.write(b"".join(RDI_OUTPUT[0:8]))
                                    new_file.write(dec_data)
                                print("File unpacked:", entry["FILENAME"])
                        else:
                            dec_data = b"".join(RDI_OUTPUT[8:])
                            with open(result_path, "wb") as new_file:
                                new_file.write(b"".join(RDI_OUTPUT[0:8]))
                                new_file.write(dec_data)
                            print("File unpacked:", entry["FILENAME"])
else:
    print("언팩 작업을 건너뜁니다.")

# === 복호화→재암호화(비암호화, 구조만 맞춤) ===
def reencrypt_from_decrypted():
    print("\n[재암호화(인크립트)] '복호화' 폴더의 파일을 zlib 압축 후, '디크립트_압축본' 구조에 맞춰 재조립합니다.")
    decrypted_folder = os.path.join("RES", "복호화")
    orig_enc_folder = os.path.join("RES", "디크립트_압축본")
    output_folder = os.path.join("RES", "재암호화_압축본")
    os.makedirs(output_folder, exist_ok=True)

    filename = input("재암호화할 파일 이름(복호화 폴더 기준): ").strip()
    decrypted_path = os.path.join(decrypted_folder, filename)
    orig_enc_path = os.path.join(orig_enc_folder, filename)
    output_path = os.path.join(output_folder, filename)

    if not os.path.isfile(decrypted_path):
        print(f"파일을 찾을 수 없습니다: {decrypted_path}")
        return
    if not os.path.isfile(orig_enc_path):
        print(f"원본 암호화 파일(디크립트_압축본)이 존재하지 않습니다: {orig_enc_path}")
        return

    with open(decrypted_path, "rb") as f:
        decrypted_full = f.read()
    if len(decrypted_full) < 32:
        print("복호화 파일이 너무 짧습니다.")
        return
    header = decrypted_full[:32]
    body = decrypted_full[32:]
    zlib_data = zlib.compress(body, level=9)
    zlib_size = len(zlib_data)

    with open(orig_enc_path, "rb") as f:
        orig_enc = bytearray(f.read())
    if len(orig_enc) < 0x20:
        print("디크립트_압축본 파일이 너무 짧습니다.")
        return

    max_size = int.from_bytes(orig_enc[0x18:0x1C], "little")
    if zlib_size > max_size:
        print(f"압축된 크기({zlib_size})가 허용 최대치({max_size})보다 큽니다. 종료합니다.")
        return

    body_start = 0x20
    orig_enc[body_start:body_start+zlib_size] = zlib_data
    orig_enc[body_start+zlib_size:body_start+max_size] = b"\x00" * (max_size - zlib_size)
    orig_enc[0x18:0x1C] = zlib_size.to_bytes(4, "little")

    with open(output_path, "wb") as f:
        f.write(orig_enc)
    print(f"재암호화(인크립트) 완료: {output_path}")

do_encrypt = input("복호화 폴더 기준으로 재암호화(인크립트) 하시겠습니까? (Y/N): ").strip().lower()
if do_encrypt == "y":
    reencrypt_from_decrypted()
else:
    print("재암호화(인크립트) 작업을 건너뜁니다.")

# === RDI 암호화 최종 처리 ===
def encrypt_final_rdi():
    print("\n[최종 암호화(인크립트)] 재암호화_압축본 파일을 RDI 암호화하여 최종_암호화본에 저장합니다.")
    input_folder = os.path.join("RES", "재암호화_압축본")
    output_folder = os.path.join("RES", "최종_암호화본")
    os.makedirs(output_folder, exist_ok=True)

    filename = input("암호화할 파일 이름(재암호화_압축본 폴더 기준): ").strip()
    input_path = os.path.join(input_folder, filename)
    output_path = os.path.join(output_folder, filename)

    if not os.path.isfile(input_path):
        print(f"파일을 찾을 수 없습니다: {input_path}")
        return

    with open(input_path, "rb") as f:
        data = f.read()
    if len(data) % 4 != 0:
        print("파일 크기가 4바이트 배수가 아닙니다.")
        return
    data_as_int = [int.from_bytes(data[i:i+4], "little") for i in range(0, len(data), 4)]

    enc_keytable = Keygen(RDI_KEY ^ GenerateKey(filename))
    encrypted_bytes = []
    for x in range(len(data_as_int)):
        enc_keytable[x % 64] = enc_keytable[x % 64] ^ enc_keytable[(x+3) % 64]
        encrypted_bytes.append((data_as_int[x] ^ enc_keytable[(x+1) % 64]).to_bytes(4, "little"))

    with open(output_path, "wb") as outf:
        outf.write(b"".join(encrypted_bytes))
    print(f"[최종 암호화본] 저장 완료: {output_path}")

do_final_encrypt = input("재암호화_압축본 파일을 RDI 방식으로 최종 암호화하시겠습니까? (Y/N): ").strip().lower()
if do_final_encrypt == "y":
    encrypt_final_rdi()
else:
    print("최종 암호화 작업을 건너뜁니다.")

# === RDB 파일 부분 덮어쓰기 기능 ===
def patch_rdb_file():
    print("\n[최종_암호화본] 폴더의 파일을 RDB 파일 원본 위치에 덮어쓰고 -m.RDB로 저장합니다.")
    filename = input("덮어쓸 파일 이름(최종_암호화본 폴더 기준): ").strip()
    patch_path = os.path.join("RES", "최종_암호화본", filename)

    # 테이블에서 파일 정보 찾기
    entry = next((e for e in TABLE if e["FILENAME"] == filename), None)
    if entry is None:
        print(f"테이블에서 파일 정보를 찾을 수 없습니다: {filename}")
        return

    # 어떤 RDB 파일, 오프셋, 크기
    def get_rdb_source_and_offset(offset):
        if offset >= 0x200000000:
            return "RES10.RDB", offset - 0x200000000
        else:
            return "RES00.RDB", offset

    if "OFFSET" not in entry:
        print("OFFSET 정보가 없습니다. 덮어쓰기 불가.")
        return

    source_rdb, real_offset = get_rdb_source_and_offset(entry["OFFSET"])
    patch_size = entry["DEC_SIZE"]

    # 원본 RDB 파일이 있는지 체크
    if not os.path.isfile(source_rdb):
        print(f"원본 RDB 파일이 없습니다: {source_rdb}")
        return

    # -m.RDB로 복사 후, 덮어쓰기
    rdb_mod_name = source_rdb.replace(".RDB", "-m.RDB")
    shutil.copy2(source_rdb, rdb_mod_name)
    with open(rdb_mod_name, "r+b") as f:
        f.seek(real_offset)
        with open(patch_path, "rb") as pfile:
            patch_data = pfile.read()
        if len(patch_data) != patch_size:
            print(f"주의: 패치 데이터 크기({len(patch_data)})가 DEC_SIZE({patch_size})와 다릅니다. ({filename})")
        # 덮어쓸 크기만큼만 기록
        f.write(patch_data[:patch_size])
    print(f"{source_rdb} → {rdb_mod_name} : {real_offset:#x} 위치에 {filename} 덮어쓰기 완료.")

do_patch_rdb = input("최종_암호화본 파일을 원본 RDB 파일에 덮어써서 -m.RDB로 저장할까요? (Y/N): ").strip().lower()
if do_patch_rdb == "y":
    patch_rdb_file()
else:
    print("RDB 덮어쓰기 작업을 건너뜁니다.")
