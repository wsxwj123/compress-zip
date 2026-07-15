"""错误契约（INTERFACE §3/§4）：每条非法输入断言正确退出码 + stderr 稳定子串。
全部 stdlib 可跑（不触发第三方后端）。也覆盖§3 校验顺序（多错并发返回哪个码）。
"""
import zipfile

import pytest

from helpers import (run_czip, compress, extract, write_file, assert_error, PW)


# ---------- compress 用法错误（argparse → 退 2，stderr 含 usage:） ----------

def test_compress_missing_format(tmp_path):
    f = write_file(tmp_path / "a.txt")
    r = run_czip("compress", "--encrypt", "none", "--", str(f))
    assert_error(r, 2, "usage:")


def test_compress_missing_encrypt(tmp_path):
    f = write_file(tmp_path / "a.txt")
    r = run_czip("compress", "--format", "zip", "--", str(f))
    assert_error(r, 2, "usage:")


def test_compress_illegal_format(tmp_path):
    f = write_file(tmp_path / "a.txt")
    r = run_czip("compress", "--format", "rar", "--encrypt", "none", "--", str(f))
    assert_error(r, 2, "usage:")


def test_compress_illegal_encrypt(tmp_path):
    f = write_file(tmp_path / "a.txt")
    r = run_czip("compress", "--format", "zip", "--encrypt", "rc4", "--", str(f))
    assert_error(r, 2, "usage:")


def test_compress_no_path():
    r = run_czip("compress", "--format", "zip", "--encrypt", "none")
    assert_error(r, 2, "usage:")


# ---------- compress 非法格式×加密组合（→ 退 5） ----------

@pytest.mark.parametrize("encrypt", ["aes", "zipcrypto"])
def test_targz_with_encryption(tmp_path, encrypt):
    f = write_file(tmp_path / "a.txt")
    r = compress("targz", encrypt, f, pw=PW)
    assert_error(r, 5, "tar.gz 不支持加密")


def test_7z_with_zipcrypto(tmp_path):
    f = write_file(tmp_path / "a.txt")
    r = compress("7z", "zipcrypto", f, pw=PW)
    assert_error(r, 5, "7z 不支持 ZipCrypto 加密")


# ---------- compress 密码缺失（→ 退 4） ----------

@pytest.mark.parametrize("encrypt", ["aes", "zipcrypto"])
def test_compress_encrypt_without_password(tmp_path, encrypt):
    f = write_file(tmp_path / "a.txt")
    r = compress("zip", encrypt, f, pw="")   # COMPRESS_PW 为空
    assert_error(r, 4, "该加密方式需要密码，但未提供")


@pytest.mark.parametrize("encrypt", ["aes", "zipcrypto"])
def test_compress_encrypt_password_unset(tmp_path, encrypt):
    """COMPRESS_PW 完全未设置也应视为"空" → 退 4。"""
    f = write_file(tmp_path / "a.txt")
    r = compress("zip", encrypt, f, pw=None)
    assert_error(r, 4, "该加密方式需要密码，但未提供")


# ---------- compress 输入不存在（→ 退 3） ----------

def test_compress_input_not_found(tmp_path):
    missing = tmp_path / "不存在的文件.txt"
    r = compress("zip", "none", missing)
    assert_error(r, 3, "找不到输入")


def test_compress_one_of_many_missing(tmp_path):
    ok = write_file(tmp_path / "ok.txt")
    missing = tmp_path / "missing.txt"
    r = compress("zip", "none", ok, missing)
    assert_error(r, 3, "找不到输入")


# ---------- compress 写入失败（→ 退 1）：--out 指向不存在的父目录 ----------

def test_compress_unwritable_out(tmp_path):
    f = write_file(tmp_path / "a.txt")
    bad_out = tmp_path / "没有这个目录" / "x.zip"
    r = compress("zip", "none", f, out=bad_out)
    assert_error(r, 1, "写入失败")


# ---------- §3 校验顺序（替用户想到的：多错并发返回哪个码） ----------

def test_order_format_before_input(tmp_path):
    """非法 format(2) 优先于 输入不存在(3)。"""
    missing = tmp_path / "nope.txt"
    r = run_czip("compress", "--format", "bad", "--encrypt", "none", "--", str(missing))
    assert_error(r, 2, "usage:")


def test_order_password_before_input(tmp_path):
    """密码缺失(4) 优先于 输入不存在(3)。"""
    missing = tmp_path / "nope.txt"
    r = compress("zip", "aes", missing, pw="")
    assert_error(r, 4, "该加密方式需要密码，但未提供")


# ---------- extract 错误 ----------

def test_extract_missing_archive():
    r = run_czip("extract")
    assert_error(r, 2, "usage:")


def test_extract_archive_not_found(tmp_path):
    r = extract(tmp_path / "不存在.zip")
    assert_error(r, 3, "找不到输入")


def test_extract_unsupported_format(tmp_path):
    bad = write_file(tmp_path / "file.xyz", b"not an archive")
    r = extract(bad)
    assert_error(r, 5, "不支持的压缩包格式")


def test_extract_corrupt_zip(tmp_path):
    """构造一个真 zip 再截断 → 中央目录损坏 → 退 1。"""
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as zf:
        zf.writestr("中文.txt", "data" * 100)
    raw = good.read_bytes()
    truncated = tmp_path / "broken.zip"
    truncated.write_bytes(raw[: len(raw) // 2])   # 砍掉后半，含中央目录
    r = extract(truncated)
    assert_error(r, 1, "压缩包损坏或不完整")
