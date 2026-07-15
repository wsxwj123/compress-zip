"""手搓 ZipCrypto 加密 zip 写入器。

背景（见 PLAN §3.2）：没有单一现成库能做「ZipCrypto 加密 + 中文名不乱码」。
pyzipper 只支持 AES 写入，系统 /usr/bin/zip 做 ZipCrypto 但中文名必乱码。
故只手搓「加密写入」这一段；解密读取继续交给标准库 zipfile / pyzipper（原生支持读 ZipCrypto）。

三个钉死的细节：
- S2 加密位与 UTF-8 bit11 共存：flag 用「按位或」加 0x1，绝不整体赋值，否则清掉 bit11 中文名又乱码。
- S3 12 字节加密头 check-byte：用 CRC-32 高字节（写入前已知完整数据，能先算 CRC）。
- R3 不实现 zip64：单成员 > 4 GiB 抛 Over4GiBError，由内核转退出码 5（提示改用 AES）。

ZipCrypto 算法（PKWARE APPNOTE / Info-ZIP）：3 个 32 位密钥 + 标准 CRC-32 逐字节更新。
"""
import os
import struct
import time
import zlib

MAX_ZIPCRYPTO_SIZE = 0xFFFFFFFF  # 4 GiB - 1；超过则无法用 32 位长度字段表示

_MASK_UTF8 = 0x800   # 通用位标志 bit 11（EFS，文件名按 UTF-8）
_BIT_ENCRYPTED = 0x1  # 通用位标志 bit 0（本条目已加密）


class Over4GiBError(Exception):
    """单成员超过 4 GiB，ZipCrypto 32 位长度字段放不下。"""


def _make_crc_table():
    table = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
        table.append(c)
    return table


_CRC_TABLE = _make_crc_table()


def _crc32_byte(crc, ch):
    """ZipCrypto 用的原始 CRC-32 单字节更新（无 zlib 的首尾取反）。"""
    return (crc >> 8) ^ _CRC_TABLE[(crc ^ ch) & 0xFF]


class _ZipCryptoCipher:
    """传统 ZipCrypto 流密码。同一实例连续 encrypt，密钥流跨调用延续。"""

    def __init__(self, password: bytes):
        self.k0, self.k1, self.k2 = 0x12345678, 0x23456789, 0x34567890
        for b in password:
            self._update(b)

    def _update(self, b):
        self.k0 = _crc32_byte(self.k0, b)
        self.k1 = (self.k1 + (self.k0 & 0xFF)) & 0xFFFFFFFF
        self.k1 = (self.k1 * 134775813 + 1) & 0xFFFFFFFF
        self.k2 = _crc32_byte(self.k2, (self.k1 >> 24) & 0xFF)

    def _keystream_byte(self):
        temp = (self.k2 | 2) & 0xFFFF
        return ((temp * (temp ^ 1)) >> 8) & 0xFF

    def encrypt(self, data: bytes) -> bytes:
        out = bytearray(len(data))
        for i, b in enumerate(data):
            out[i] = b ^ self._keystream_byte()
            self._update(b)  # 用明文字节更新密钥
        return bytes(out)


def _encode_name_flags(arcname: str):
    """复刻 zipfile._encodeFilenameFlags：能 ASCII 就 ASCII，否则 UTF-8 + 置 bit11。
    不依赖标准库私有方法，行为一致。"""
    try:
        return arcname.encode("ascii"), 0
    except UnicodeEncodeError:
        return arcname.encode("utf-8"), _MASK_UTF8


def _dos_datetime(ts):
    t = time.localtime(ts)
    if t.tm_year < 1980:
        return 0, (1 << 5) | 1  # 1980-01-01 00:00
    dosdate = ((t.tm_year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday
    dostime = (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)
    return dostime, dosdate


def write_zipcrypto(out_path, entries, password: bytes):
    """把 entries 写成 ZipCrypto 加密 zip。

    entries: [(src_path_or_None, arcname, is_dir), ...]
    - is_dir=True：src 为 None，写空目录条目（目录不加密）。
    - 文件：读原文→deflate→前置 12 字节加密头→整体 ZipCrypto 加密→写入。
    """
    central = []  # 中央目录记录
    now = time.time()
    with open(out_path, "wb") as fp:
        for src, arcname, is_dir in entries:
            name_bytes, flag = _encode_name_flags(arcname)
            offset = fp.tell()
            if is_dir:
                dostime, dosdate = _dos_datetime(now)
                _write_local_header(fp, name_bytes, flag, method=0,
                                    dostime=dostime, dosdate=dosdate,
                                    crc=0, csize=0, usize=0)
                central.append((name_bytes, flag, 0, dostime, dosdate, 0, 0, 0,
                                offset, True))
                continue

            size = os.path.getsize(src)
            if size > MAX_ZIPCRYPTO_SIZE:
                raise Over4GiBError(src)
            with open(src, "rb") as f:
                data = f.read()
            crc = zlib.crc32(data) & 0xFFFFFFFF
            co = zlib.compressobj(6, zlib.DEFLATED, -15)
            compressed = co.compress(data) + co.flush()

            cipher = _ZipCryptoCipher(password)
            header = bytearray(os.urandom(11))
            header.append((crc >> 24) & 0xFF)  # S3: check-byte = CRC 高字节
            enc = cipher.encrypt(bytes(header)) + cipher.encrypt(compressed)

            csize = len(enc)
            usize = len(data)
            eflag = flag | _BIT_ENCRYPTED  # S2: 按位或，保留 bit11
            dostime, dosdate = _dos_datetime(now)
            _write_local_header(fp, name_bytes, eflag, method=8,
                                dostime=dostime, dosdate=dosdate,
                                crc=crc, csize=csize, usize=usize)
            fp.write(enc)
            central.append((name_bytes, eflag, 8, dostime, dosdate, crc, csize,
                            usize, offset, False))

        _write_central_dir(fp, central)


def _write_local_header(fp, name_bytes, flag, method, dostime, dosdate,
                        crc, csize, usize):
    fp.write(struct.pack("<4sHHHHHIIIHH",
                         b"PK\x03\x04", 20, flag, method, dostime, dosdate,
                         crc, csize, usize, len(name_bytes), 0))
    fp.write(name_bytes)


def _write_central_dir(fp, central):
    cd_start = fp.tell()
    for (name_bytes, flag, method, dostime, dosdate, crc, csize, usize,
         offset, is_dir) in central:
        ext_attr = 0x10 if is_dir else 0  # 目录属性位
        fp.write(struct.pack("<4sHHHHHHIIIHHHHHII",
                             b"PK\x01\x02", 20, 20, flag, method, dostime,
                             dosdate, crc, csize, usize, len(name_bytes),
                             0, 0, 0, 0, ext_attr, offset))
        fp.write(name_bytes)
    cd_size = fp.tell() - cd_start
    fp.write(struct.pack("<4sHHHHIIH",
                         b"PK\x05\x06", 0, 0, len(central), len(central),
                         cd_size, cd_start, 0))


def _self_check():
    """自检（PLAN S3）：加密含中文名小文件 → 标准库 zipfile 同密码解出、内容一致、
    bit11 置位、错误密码解失败；>4GiB 走桩验证抛 Over4GiBError。"""
    import tempfile
    import zipfile

    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "中文文件.txt")
        payload = "秘密内容 secret 🔒".encode("utf-8")
        with open(src, "wb") as f:
            f.write(payload)
        arc = os.path.join(d, "out.zip")
        pw = "P@ss中文123🔒".encode("utf-8")
        write_zipcrypto(arc, [(src, "中文文件.txt", False)], pw)

        with zipfile.ZipFile(arc) as zf:
            info = zf.infolist()[0]
            assert info.filename == "中文文件.txt", info.filename
            assert info.flag_bits & _MASK_UTF8 == _MASK_UTF8, hex(info.flag_bits)
            assert info.flag_bits & _BIT_ENCRYPTED == _BIT_ENCRYPTED
            zf.setpassword(pw)
            assert zf.read("中文文件.txt") == payload, "解出内容不一致"

        with zipfile.ZipFile(arc) as zf:
            zf.setpassword(b"wrong-password")
            try:
                zf.read("中文文件.txt")
                raise AssertionError("错误密码竟解成功")
            except RuntimeError:
                pass  # 预期：密码错

        # >4GiB 桩：伪造 getsize 返回超限，断言抛 Over4GiBError（不真造大文件）
        real_getsize = os.path.getsize
        os.path.getsize = lambda p: MAX_ZIPCRYPTO_SIZE + 1
        try:
            write_zipcrypto(os.path.join(d, "big.zip"),
                            [(src, "big.bin", False)], pw)
            raise AssertionError("未对 >4GiB 抛 Over4GiBError")
        except Over4GiBError:
            pass
        finally:
            os.path.getsize = real_getsize

    print("zipcrypto self-check OK")


if __name__ == "__main__":
    _self_check()
